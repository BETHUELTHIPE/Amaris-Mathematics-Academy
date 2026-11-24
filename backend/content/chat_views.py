from uuid import UUID

from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_vary_headers
from django.utils.crypto import constant_time_compare, salted_hmac
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import serializers, status
from rest_framework.authentication import get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import SupabaseStudentAuthentication, SupabaseStudentPrincipal
from .chat_models import CHAT_MESSAGE_LIMIT, CHAT_PAGE_SIZE, ChatMessage, ChatRoom
from .models import LiveClassBooking
from .tutor_views import TUTOR_GROUP, find_approved_tutors

CHAT_BOOKING_STATUSES = (LiveClassBooking.Status.CONFIRMED, LiveClassBooking.Status.COMPLETED)
BOOKINGS_PER_PAGE = 20


class ChatAuthentication(SupabaseStudentAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != self.keyword:
            raise AuthenticationFailed("A verified Supabase session is required.")
        try:
            token = header[1].decode("ascii")
        except UnicodeDecodeError as exc:
            raise AuthenticationFailed("Invalid chat session.") from exc
        payload = self._validate_token(token)
        email = str(payload.get("email") or "").strip().lower()
        if not payload.get("id") or not email or not payload.get("email_confirmed_at"):
            raise AuthenticationFailed("Verify your email before opening Messages.")
        try:
            user_id = str(UUID(str(payload["id"])))
        except ValueError as exc:
            raise AuthenticationFailed("Invalid chat account.") from exc

        tutors = find_approved_tutors(email)
        if len(tutors) > 1:
            raise AuthenticationFailed("This chat account could not be matched to an approved tutor.")
        if tutors:
            return tutors[0], ChatMessage.Sender.TUTOR

        student = self._get_or_create_student(payload, user_id, email)
        if not student.is_active:
            raise AuthenticationFailed("This student profile is inactive.")
        return SupabaseStudentPrincipal(student, user_id, email), ChatMessage.Sender.STUDENT


class RoomQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(min_value=1, max_value=100000, default=1)


class BookingRoomSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    topic = serializers.CharField()
    participant = serializers.CharField()
    starts_at = serializers.DateTimeField()
    assignment = serializers.CharField()


class RoomsSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=("student", "tutor"))
    bookings = BookingRoomSerializer(many=True)
    has_next = serializers.BooleanField()


class MessageQuerySerializer(serializers.Serializer):
    before = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)
    after = serializers.IntegerField(min_value=1, max_value=2**63 - 1, required=False)

    def validate(self, attrs):
        if "before" in attrs and "after" in attrs:
            raise serializers.ValidationError("Specify one message cursor.")
        return attrs


class MessageInputSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict) and "text" in data and not isinstance(data["text"], str):
            raise serializers.ValidationError({"text": "Enter a text message."})
        return super().to_internal_value(data)

    text = serializers.CharField(max_length=CHAT_MESSAGE_LIMIT)
    client_id = serializers.UUIDField()


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.CharField(read_only=True)

    class Meta:
        model = ChatMessage
        fields = ("id", "sender", "text", "sent_at")


class MessagePageSerializer(serializers.Serializer):
    messages = MessageSerializer(many=True)
    has_more = serializers.BooleanField()


def chat_bookings():
    return (
        LiveClassBooking.objects.filter(
            status__in=CHAT_BOOKING_STATUSES,
            student__is_active=True,
            slot__tutor__is_active=True,
        )
        .filter(slot__tutor__groups__name=TUTOR_GROUP)
        .select_related("student", "slot__tutor")
    )


def booking_participants(booking):
    return {"booking_id": booking.pk, "student_id": booking.student_id, "tutor_id": booking.slot.tutor_id}


def booking_assignment(booking):
    value = f"{booking.pk}:{booking.student_id}:{booking.slot.tutor_id}"
    return salted_hmac("amaris.booking.chat", value, algorithm="sha256").hexdigest()


def booking_is_current(room):
    return chat_bookings().filter(pk=room.booking_id, student_id=room.student_id, slot__tutor_id=room.tutor_id).exists()


def append_message(room, *, sender, text, client_id, admin=None):
    # Serialize writes within a room so cursor polling sees committed IDs in order.
    with transaction.atomic():
        room = ChatRoom.objects.select_for_update().get(pk=room.pk)
        message, created = room.messages.get_or_create(
            sender=sender, client_id=client_id, defaults={"text": text, "admin": admin}
        )
        if created:
            room.last_activity_at = message.sent_at
            room.save(update_fields=["last_activity_at"])
        return message, created


def message_page(room, *, before=None, after=None):
    if room is None:
        return [], False
    messages = room.messages.all()
    if after is not None:
        items = list(messages.filter(pk__gt=after).order_by("pk")[: CHAT_PAGE_SIZE + 1])
        return items[:CHAT_PAGE_SIZE], len(items) > CHAT_PAGE_SIZE
    if before is not None:
        messages = messages.filter(pk__lt=before)
    items = list(messages.order_by("-pk")[: CHAT_PAGE_SIZE + 1])
    return list(reversed(items[:CHAT_PAGE_SIZE])), len(items) > CHAT_PAGE_SIZE


class ChatAPIView(APIView):
    authentication_classes = (ChatAuthentication,)
    permission_classes = (IsAuthenticated,)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Authorization",))
        return response

    @staticmethod
    def scoped_bookings(request):
        lookup = (
            {"student_id": request.user.pk}
            if request.auth == ChatMessage.Sender.STUDENT
            else {"slot__tutor_id": request.user.pk}
        )
        return chat_bookings().filter(**lookup)


class ChatRoomsView(ChatAPIView):
    @extend_schema(parameters=[RoomQuerySerializer], responses=RoomsSerializer)
    def get(self, request):
        query = RoomQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        offset = (query.validated_data["page"] - 1) * BOOKINGS_PER_PAGE
        bookings = list(
            self.scoped_bookings(request).order_by("-slot__starts_at", "pk")[offset : offset + BOOKINGS_PER_PAGE + 1]
        )
        return Response(
            {
                "role": request.auth,
                "bookings": BookingRoomSerializer(
                    [
                        {
                            "id": booking.pk,
                            "topic": booking.topic,
                            "participant": (
                                booking.slot.tutor.get_full_name().strip() or "Assigned tutor"
                                if request.auth == ChatMessage.Sender.STUDENT
                                else f"{booking.student.first_name} {booking.student.last_name}".strip()
                            ),
                            "starts_at": booking.slot.starts_at,
                            "assignment": booking_assignment(booking),
                        }
                        for booking in bookings[:BOOKINGS_PER_PAGE]
                    ],
                    many=True,
                ).data,
                "has_next": len(bookings) > BOOKINGS_PER_PAGE,
            }
        )


class ChatMessagesView(ChatAPIView):
    parser_classes = (JSONParser,)

    def room_scope(self, request, booking_id):
        if booking_id is not None:
            booking = get_object_or_404(self.scoped_bookings(request), pk=booking_id)
            if not constant_time_compare(request.query_params.get("assignment", ""), booking_assignment(booking)):
                raise Http404
            return booking_participants(booking)
        if request.auth == ChatMessage.Sender.STUDENT:
            return {"booking_id": None, "student_id": request.user.pk, "tutor_id": None}
        return {"booking_id": None, "student_id": None, "tutor_id": request.user.pk}

    @extend_schema(
        parameters=[MessageQuerySerializer], responses=MessagePageSerializer, operation_id="chat_support_read"
    )
    def get(self, request, booking_id=None):
        scope = self.room_scope(request, booking_id)
        query = MessageQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        room = ChatRoom.objects.filter(**scope).first()
        messages, has_more = message_page(room, **query.validated_data)
        return Response({"messages": MessageSerializer(messages, many=True).data, "has_more": has_more})

    @extend_schema(
        request=MessageInputSerializer,
        responses={200: MessageSerializer, 201: MessageSerializer},
        operation_id="chat_support_send",
    )
    def post(self, request, booking_id=None):
        scope = self.room_scope(request, booking_id)
        serializer = MessageInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        room, _ = ChatRoom.objects.get_or_create(**scope)
        with transaction.atomic():
            if booking_id is not None and not booking_is_current(room):
                raise Http404
            message, created = append_message(room, sender=request.auth, **serializer.validated_data)
        if message.text != serializer.validated_data["text"]:
            return Response({"detail": "This message key has already been used."}, status=status.HTTP_409_CONFLICT)
        return Response(
            MessageSerializer(message).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


BOOKING_ASSIGNMENT_PARAMETER = OpenApiParameter(
    "assignment", str, description="Current booking assignment from the chat room list.", required=True
)


class BookingChatMessagesView(ChatMessagesView):
    @extend_schema(
        parameters=[MessageQuerySerializer, BOOKING_ASSIGNMENT_PARAMETER],
        responses=MessagePageSerializer,
        operation_id="chat_booking_read",
    )
    def get(self, request, booking_id):
        return super().get(request, booking_id)

    @extend_schema(
        request=MessageInputSerializer,
        responses={200: MessageSerializer, 201: MessageSerializer},
        operation_id="chat_booking_send",
        parameters=[BOOKING_ASSIGNMENT_PARAMETER],
    )
    def post(self, request, booking_id):
        return super().post(request, booking_id)

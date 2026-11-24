import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

CHAT_MESSAGE_LIMIT = 2000
CHAT_PAGE_SIZE = 50


class ChatRoom(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey("LiveClassBooking", blank=True, null=True, on_delete=models.PROTECT)
    student = models.ForeignKey("StudentRecord", blank=True, null=True, on_delete=models.PROTECT)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    class Meta:
        verbose_name = "chat room"
        ordering = ("-last_activity_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(booking__isnull=False, student__isnull=False, tutor__isnull=False)
                    | Q(booking__isnull=True, student__isnull=False, tutor__isnull=True)
                    | Q(booking__isnull=True, student__isnull=True, tutor__isnull=False)
                ),
                name="chat_room_valid_participants",
            ),
            models.UniqueConstraint(fields=["booking", "student", "tutor"], name="chat_booking_participants_unique"),
            models.UniqueConstraint(
                fields=["student"], condition=Q(booking__isnull=True), name="chat_student_support_unique"
            ),
            models.UniqueConstraint(
                fields=["tutor"], condition=Q(booking__isnull=True), name="chat_tutor_support_unique"
            ),
        ]

    def __str__(self):
        booking = self.booking
        if booking is not None:
            return f"Booking {booking.reference}"
        return f"Support for {self.student or self.tutor}"


class ChatMessage(models.Model):
    class Sender(models.TextChoices):
        STUDENT = "student", "Student"
        TUTOR = "tutor", "Tutor"
        ADMIN = "admin", "Academy Admin"

    room = models.ForeignKey(ChatRoom, related_name="messages", on_delete=models.PROTECT, db_index=False)
    sender = models.CharField(max_length=7, choices=Sender.choices)
    admin = models.ForeignKey(settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT)
    client_id = models.UUIDField(editable=False)
    text = models.CharField(max_length=CHAT_MESSAGE_LIMIT)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["room", "id"], name="chat_room_message_idx")]
        constraints = [
            models.CheckConstraint(
                condition=Q(sender="admin", admin__isnull=False)
                | Q(sender__in=("student", "tutor"), admin__isnull=True),
                name="chat_message_valid_sender",
            ),
            models.UniqueConstraint(fields=["room", "sender", "client_id"], name="chat_message_client_unique"),
        ]

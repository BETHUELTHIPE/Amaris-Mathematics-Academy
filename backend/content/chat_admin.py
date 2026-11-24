import uuid

from django import forms
from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from .chat_models import CHAT_MESSAGE_LIMIT, ChatMessage, ChatRoom
from .chat_views import append_message, booking_is_current, booking_participants, chat_bookings, message_page
from .tutor_views import TUTOR_GROUP


class ChatRoomForm(forms.ModelForm):
    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        booking, student, tutor = (data.get(key) for key in ("booking", "student", "tutor"))
        if booking:
            if student or tutor:
                raise forms.ValidationError("Choose a booking by itself for a session room.")
            if not chat_bookings().filter(pk=booking.pk).exists():
                raise forms.ValidationError("Choose a confirmed or completed booking with an approved tutor.")
            data.update(student=booking.student, tutor=booking.slot.tutor)
        elif bool(student) == bool(tutor):
            raise forms.ValidationError("Choose one student or one tutor for a support room.")
        elif student and not student.is_active:
            raise forms.ValidationError("Choose an active student.")
        elif tutor and not (tutor.is_active and tutor.groups.filter(name=TUTOR_GROUP).exists()):
            raise forms.ValidationError("Choose an active, approved tutor.")
        return data


class AdminReplyForm(forms.Form):
    text = forms.CharField(
        label="Reply",
        max_length=CHAT_MESSAGE_LIMIT,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Write a message"}),
    )
    client_id = forms.UUIDField(widget=forms.HiddenInput)


class AdminHistoryQuery(forms.Form):
    before = forms.IntegerField(min_value=1, max_value=2**63 - 1, required=False)


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    form = ChatRoomForm
    list_display = ("__str__", "student", "tutor", "last_activity_at")
    list_select_related = ("booking", "student", "tutor")
    search_fields = ("booking__reference", "student__email", "tutor__email")
    fields = ("booking", "student", "tutor")
    raw_id_fields = fields
    list_per_page = 25
    actions = None

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        scope = (
            booking_participants(obj.booking)
            if obj.booking_id
            else {"booking_id": None, "student_id": obj.student_id, "tutor_id": obj.tutor_id}
        )
        room, _ = ChatRoom.objects.get_or_create(**scope)
        obj.pk = room.pk
        obj.last_activity_at = room.last_activity_at

    def change_view(self, request, object_id, form_url="", extra_context=None):
        if not self.has_view_permission(request):
            raise PermissionDenied
        room = self.get_object(request, object_id)
        if room is None:
            raise Http404
        thread_url = reverse("admin:content_chatroom_change", args=[room.pk])
        can_reply = not room.booking_id or booking_is_current(room)
        form = AdminReplyForm(request.POST if request.method == "POST" else None, initial={"client_id": uuid.uuid4()})
        if request.method == "POST":
            if not can_reply:
                raise PermissionDenied
            if form.is_valid():
                message, _ = append_message(
                    room, sender=ChatMessage.Sender.ADMIN, admin=request.user, **form.cleaned_data
                )
                if message.admin_id == request.user.pk and message.text == form.cleaned_data["text"]:
                    return redirect(thread_url)
                form.add_error(None, "This reply key has already been used. Reload the room to send another reply.")

        query = AdminHistoryQuery(request.GET)
        if not query.is_valid():
            raise Http404
        entries, older = message_page(room, before=query.cleaned_data["before"])
        return TemplateResponse(
            request,
            "admin/content/chatroom/thread.html",
            {
                **self.admin_site.each_context(request),
                "opts": self.model._meta,
                "title": str(room),
                "thread_url": thread_url,
                "entries": entries,
                "older": entries[0].pk if older else None,
                "form": form,
                "can_reply": can_reply,
            },
        )


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    # Messages are only displayed and submitted through the room interface.
    def has_module_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return False

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

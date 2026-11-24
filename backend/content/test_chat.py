import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from .authentication import SupabaseStudentAuthentication
from .chat_models import CHAT_PAGE_SIZE, ChatMessage, ChatRoom
from .chat_views import booking_assignment
from .models import LiveClassBooking, StudentRecord, TutorAvailabilitySlot

LOCAL_CACHE = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


@override_settings(CACHES=LOCAL_CACHE)
class ChatTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        group = Group.objects.create(name="Tutors")
        cls.tutor = users.create_user("tutor", email="tutor@example.test", first_name="Ada")
        cls.other_tutor = users.create_user("other-tutor", email="other-tutor@example.test")
        cls.tutor.groups.add(group)
        cls.other_tutor.groups.add(group)
        cls.admin = users.create_superuser("admin", email="admin@example.test")
        cls.staff = users.create_user("staff", email="staff@example.test", is_staff=True)
        cls.student = cls.make_student("student")
        cls.other_student = cls.make_student("other-student")
        cls.booking = cls.make_booking(cls.student, cls.tutor, 1)
        cls.other_booking = cls.make_booking(cls.other_student, cls.tutor, 2)
        cls.pending = cls.make_booking(cls.student, cls.tutor, 3, LiveClassBooking.Status.PENDING_PAYMENT)

    @staticmethod
    def make_student(name):
        return StudentRecord.objects.create(
            supabase_user_id=uuid.uuid4(), email=f"{name}@example.test", first_name=name, last_name="Example"
        )

    @staticmethod
    def make_booking(student, tutor, offset, status=LiveClassBooking.Status.CONFIRMED):
        start = timezone.now() + timedelta(days=offset)
        slot = TutorAvailabilitySlot.objects.create(
            tutor=tutor,
            programme="caps",
            subject="mathematics",
            level="Grade 12",
            starts_at=start,
            ends_at=start + timedelta(hours=1),
        )
        return LiveClassBooking.objects.create(
            slot=slot,
            student=student,
            reference=f"CHAT-{offset}",
            idempotency_key=f"chat-{offset}",
            topic=f"Topic {offset}",
            programme=slot.programme,
            subject=slot.subject,
            level=slot.level,
            status=status,
        )

    def api(self, method, url, actor, data=None, *, verified=True):
        profile = {
            "id": str(getattr(actor, "supabase_user_id", uuid.uuid4())),
            "email": actor.email,
            "email_confirmed_at": "2026-11-24T11:00:00Z" if verified else None,
            "user_metadata": {"role": "admin"},
        }
        with patch.object(SupabaseStudentAuthentication, "_validate_token", return_value=profile):
            return getattr(APIClient(), method)(
                url, data=data, format="json", secure=True, HTTP_AUTHORIZATION="Bearer chat-test-token"
            )

    def url(self, booking=None):
        if booking is None:
            return reverse("chat-support-messages")
        path = reverse("chat-booking-messages", args=[booking.pk])
        return f"{path}?assignment={booking_assignment(booking)}"

    def send(self, actor, text, booking=None, **extra):
        return self.api("post", self.url(booking), actor, {"text": text, "client_id": str(uuid.uuid4()), **extra})

    def test_verified_email_and_server_side_tutor_role_required(self):
        rooms = reverse("chat-rooms")
        self.assertEqual(APIClient().get(rooms, secure=True).status_code, 401)
        self.assertEqual(self.api("get", rooms, self.student, verified=False).status_code, 401)
        self.assertEqual(self.api("get", rooms, self.student).data["role"], "student")
        self.assertEqual(self.api("get", rooms, self.tutor).data["role"], "tutor")
        self.assertEqual(StudentRecord.objects.count(), 2)
        duplicate = get_user_model().objects.create_user("duplicate", email=self.tutor.email.upper())
        duplicate.groups.add(self.tutor.groups.get())
        self.assertEqual(self.api("get", rooms, self.tutor).status_code, 401)

    def test_only_booking_participants_see_its_conversation(self):
        private_message = "Only for this class"
        sent = self.send(self.student, private_message, self.booking, sender="admin", student_id=self.other_student.pk)
        self.assertEqual(sent.status_code, 201)
        self.assertEqual(sent.data["sender"], "student")
        reply = self.send(self.tutor, "Tutor reply", self.booking)
        self.assertEqual(reply.data["sender"], "tutor")
        reader = self.api("get", self.url(self.booking), self.student)
        self.assertEqual(reader.status_code, 200)
        self.assertEqual([message["text"] for message in reader.data["messages"]], [private_message, "Tutor reply"])
        self.assertEqual(reader["Cache-Control"], "private, no-store")
        for actor in (self.other_student, self.other_tutor):
            with self.subTest(actor=actor):
                self.assertEqual(self.api("get", self.url(self.booking), actor).status_code, 404)
                self.assertEqual(self.send(actor, "Intrusion attempt", self.booking).status_code, 404)
        self.assertEqual(self.api("get", self.url(self.other_booking), self.student).status_code, 404)
        self.assertEqual(self.send(self.student, "Pending", self.pending).status_code, 404)
        self.assertEqual(ChatMessage.objects.count(), 2)
        student_rooms = self.api("get", reverse("chat-rooms"), self.student)
        self.assertEqual([item["id"] for item in student_rooms.data["bookings"]], [str(self.booking.pk)])
        tutor_rooms = self.api("get", reverse("chat-rooms"), self.tutor)
        self.assertCountEqual(
            [item["id"] for item in tutor_rooms.data["bookings"]],
            [str(self.booking.pk), str(self.other_booking.pk)],
        )

    def test_tutor_reassignment_and_role_removal_do_not_expose_messages(self):
        self.assertEqual(self.send(self.student, "Old tutor's thread", self.booking).status_code, 201)
        old_assignment = self.url(self.booking)
        self.booking.slot.tutor = self.other_tutor
        self.booking.slot.save(update_fields=["tutor"])
        self.assertEqual(self.api("get", old_assignment, self.student).status_code, 404)
        reply = {"text": "Addressed to my previous tutor", "client_id": str(uuid.uuid4())}
        self.assertEqual(self.api("post", old_assignment, self.student, reply).status_code, 404)
        self.assertEqual(self.api("get", self.url(self.booking), self.tutor).status_code, 404)
        self.assertEqual(self.api("get", self.url(self.booking), self.other_tutor).data["messages"], [])
        self.assertEqual(self.send(self.other_tutor, "New tutor's thread", self.booking).status_code, 201)
        self.assertEqual(
            [entry["text"] for entry in self.api("get", self.url(self.booking), self.student).data["messages"]],
            ["New tutor's thread"],
        )
        self.other_tutor.groups.clear()
        self.assertEqual(self.api("get", self.url(self.booking), self.other_tutor).status_code, 404)

    def test_support_is_isolated_and_send_retries_are_idempotent(self):
        key = str(uuid.uuid4())
        self.assertEqual(self.send(self.student, "My support message", client_id=key).status_code, 201)
        self.assertEqual(self.send(self.student, "My support message", client_id=key).status_code, 200)
        self.assertEqual(self.send(self.student, "Changed", client_id=key).status_code, 409)
        for invalid in (" ", "x" * 2001, 245):
            self.assertEqual(self.send(self.student, invalid).status_code, 400)
        for account in (self.other_student, self.tutor):
            self.assertEqual(self.api("get", self.url(), account).data["messages"], [])
            self.assertEqual(self.send(account, "Separate support", client_id=key).status_code, 201)
        self.assertEqual(ChatRoom.objects.count(), 3)
        self.assertEqual(ChatMessage.objects.count(), 3)

    def test_django_admin_inbox_reply_and_superuser_boundary(self):
        self.assertEqual(self.send(self.student, "<script>alert(1)</script>", self.booking).status_code, 201)
        room = ChatRoom.objects.get()
        inbox = reverse("admin:content_chatroom_changelist")
        thread = reverse("admin:content_chatroom_change", args=[room.pk])
        for method in ("get", "post"):
            self.client.force_login(self.staff)
            self.assertEqual(getattr(self.client, method)(thread, secure=True).status_code, 403)
        self.assertEqual(self.client.get(inbox, secure=True).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(inbox, secure=True), self.booking.reference)
        self.assertContains(self.client.get(thread, secure=True), "&lt;script&gt;alert(1)&lt;/script&gt;")
        reply = {"text": "Admin reply", "client_id": str(uuid.uuid4())}
        self.assertEqual(self.client.post(thread, reply, secure=True).status_code, 302)
        self.assertEqual(self.client.post(thread, reply, secure=True).status_code, 302)
        self.assertEqual(ChatMessage.objects.filter(admin=self.admin).count(), 1)
        data = self.api("get", self.url(self.booking), self.tutor).data["messages"]
        self.assertEqual((data[-1]["sender"], data[-1]["text"]), ("admin", reply["text"]))
        self.assertNotIn("admin", data[-1])

    def test_admin_can_open_a_support_or_booking_conversation(self):
        self.client.force_login(self.admin)
        url = reverse("admin:content_chatroom_add")
        for fields in ({"student": self.student.pk}, {"booking": self.booking.pk}, {"tutor": self.tutor.pk}):
            result = self.client.post(url, fields, secure=True)
            self.assertEqual(result.status_code, 302, getattr(result, "context_data", None))
        self.assertEqual(ChatRoom.objects.count(), 3)
        # A support room has one non-admin participant.
        result = self.client.post(url, {"student": self.other_student.pk, "tutor": self.other_tutor.pk}, secure=True)
        self.assertContains(result, "Choose one student or one tutor for a support room.")
        self.assertEqual(ChatRoom.objects.count(), 3)

    def test_message_cursors_bound_history_and_return_messages_in_order(self):
        self.send(self.student, "First")
        room = ChatRoom.objects.get()
        ChatMessage.objects.bulk_create(
            [
                ChatMessage(room=room, sender="student", client_id=uuid.uuid4(), text=str(i))
                for i in range(CHAT_PAGE_SIZE)
            ]
        )
        latest = self.api("get", self.url(), self.student).data
        self.assertEqual(len(latest["messages"]), CHAT_PAGE_SIZE)
        self.assertTrue(latest["has_more"])
        oldest_visible = latest["messages"][0]["id"]
        earlier = self.api("get", f"{self.url()}?before={oldest_visible}", self.student).data
        self.assertEqual([message["text"] for message in earlier["messages"]], ["First"])
        self.assertFalse(earlier["has_more"])
        self.send(self.student, "Newest")
        next_page = self.api("get", f"{self.url()}?after={latest['messages'][-1]['id']}", self.student).data
        self.assertEqual([message["text"] for message in next_page["messages"]], ["Newest"])
        self.assertEqual(self.api("get", f"{self.url()}?after=1&before=2", self.student).status_code, 400)

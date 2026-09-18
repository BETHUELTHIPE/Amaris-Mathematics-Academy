from unittest.mock import patch

from django.test import TestCase, override_settings

from content.models import ContactEnquiry
from content.serializers import ContactEnquirySerializer


@override_settings(
    AI_ENQUIRY_AUTOREPLY_ENABLED=True,
    OPENAI_API_KEY="test-openai-key",
    OPENAI_ENQUIRY_MODEL="gpt-5.6-luna",
    EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend",
    EMAIL_HOST="smtp.example.com",
    EMAIL_HOST_USER="mailer@example.com",
    EMAIL_HOST_PASSWORD="test-password",
    DEFAULT_FROM_EMAIL="Amaris Mathematics Academy <mailer@example.com>",
)
class EnquiryAutoReplyTests(TestCase):
    @patch("content.services.enquiry_autoreply.EmailMessage.send", return_value=1)
    @patch(
        "content.services.enquiry_autoreply._call_openai",
        return_value=(
            "Hello Student,\n\nWe can help with the published mathematics courses.\n\nKind regards,\nAmaris Mathematics Academy",
            "resp_test_123",
        ),
    )
    @patch(
        "content.services.enquiry_autoreply.build_website_context",
        return_value="Academy: Amaris Mathematics Academy\nPublished courses: Grade 12 Mathematics",
    )
    def test_contact_serializer_saves_and_sends_grounded_auto_reply(self, _context, _openai, send):
        serializer = ContactEnquirySerializer(
            data={
                "name": "Synthetic Student",
                "email": "synthetic.student@example.com",
                "phone": "0710000000",
                "subject": "course guidance",
                "message": "Please help me choose the correct mathematics course for my level.",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        enquiry = serializer.save()

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, ContactEnquiry.Status.IN_PROGRESS)
        self.assertIn("AI AUTO-REPLY SENT", enquiry.admin_notes)
        self.assertIn("resp_test_123", enquiry.admin_notes)
        send.assert_called_once_with(fail_silently=False)

    @override_settings(OPENAI_API_KEY="")
    @patch("content.services.enquiry_autoreply.EmailMessage.send")
    def test_contact_enquiry_is_preserved_when_openai_is_not_configured(self, send):
        serializer = ContactEnquirySerializer(
            data={
                "name": "Synthetic Student",
                "email": "synthetic.student2@example.com",
                "phone": "",
                "subject": "technical support",
                "message": "I can open the website but I need help finding the correct support page.",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        enquiry = serializer.save()

        enquiry.refresh_from_db()
        self.assertEqual(enquiry.status, ContactEnquiry.Status.NEW)
        self.assertIn("OPENAI_API_KEY is not configured", enquiry.admin_notes)
        send.assert_not_called()

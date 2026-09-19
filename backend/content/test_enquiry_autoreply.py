from unittest.mock import patch

from django.test import TestCase, override_settings

from content.models import ContactEnquiry, Course, CourseCategory, Page, PageSection, SiteSettings
from content.serializers import ContactEnquirySerializer
from content.services.enquiry_autoreply import build_website_context


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

    @override_settings(PUBLIC_SITE_URL="https://academy.example.test")
    def test_website_context_includes_registration_verification_and_purchase_workflow(self):
        SiteSettings.objects.create(
            site_name="Amaris Mathematics Academy",
            phone="071 415 6665",
            email="support@example.test",
            business_hours="Mon-Sun, 07:00-20:00",
        )
        category = CourseCategory.objects.create(name="CAPS", slug="caps")
        Course.objects.create(
            category=category,
            title="Grade 12 Mathematics",
            slug="grade-12-mathematics",
            short_description="Exam-focused Grade 12 mathematics.",
            description="Structured Grade 12 mathematics course.",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            estimated_hours=20,
            status=Course.Status.PUBLISHED,
        )

        context = build_website_context()

        self.assertIn("Official website student workflow:", context)
        self.assertIn("https://academy.example.test/register", context)
        self.assertIn("six-digit verification code", context)
        self.assertIn("secure confirmation link", context)
        self.assertIn("https://academy.example.test/login", context)
        self.assertIn("https://academy.example.test/courses", context)
        self.assertIn("https://academy.example.test/checkout/<course-slug>", context)
        self.assertIn("continues to PayFast", context)
        self.assertIn("only after the server verifies the PayFast notification", context)
        self.assertIn("https://academy.example.test/dashboard", context)
        self.assertIn(
            "url=https://academy.example.test/courses/grade-12-mathematics",
            context,
        )

    @override_settings(PUBLIC_SITE_URL="https://academy.example.test")
    def test_website_context_includes_published_page_ctas_and_structured_content(self):
        page = Page.objects.create(
            title="How it works",
            slug="how-it-works",
            summary="Learn how to join Amaris.",
            is_published=True,
        )
        PageSection.objects.create(
            page=page,
            section_key="registration",
            heading="Create your profile",
            body="Register and verify your email before enrolling.",
            call_to_action_label="Register",
            call_to_action_url="/register",
            content={"steps": ["Register", "Verify email", "Choose a course"]},
            is_published=True,
        )

        context = build_website_context()

        self.assertIn("url=https://academy.example.test/how-it-works", context)
        self.assertIn("CTA=Register -> https://academy.example.test/register", context)
        self.assertIn("structured_content=", context)
        self.assertIn("Choose a course", context)

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

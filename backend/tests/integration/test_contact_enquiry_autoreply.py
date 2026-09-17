import os
from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import TestCase

from content.models import ContactEnquiry, Course, CourseCategory, FAQ, PricingPlan, SiteSettings
from content.services.enquiry_autoreply import build_enquiry_reply_context
from content.tasks import send_contact_enquiry_auto_reply


class ContactEnquiryAutoReplyTests(TestCase):
    def setUp(self):
        cache.clear()
        mail.outbox = []
        self.site = SiteSettings.objects.create(
            site_name="Amaris Mathematics Academy",
            email="support@example.com",
            phone="071 000 0000",
            website_url="https://example.com",
            business_hours="Mon-Sun, 07:00-20:00",
        )
        self.category = CourseCategory.objects.create(name="Mathematics", slug="mathematics")
        self.course = Course.objects.create(
            category=self.category,
            title="Grade 12 Calculus Mastery",
            slug="grade-12-calculus-mastery",
            short_description="Focused calculus revision for Grade 12 learners.",
            description="Functions, derivatives and exam-style calculus practice.",
            curriculum="CAPS",
            academic_level="Grade 12",
            price="450.00",
            status=Course.Status.PUBLISHED,
        )
        self.plan = PricingPlan.objects.create(
            name="Exam Pack",
            slug="exam-pack",
            description="Exam preparation package with guided revision.",
            price="950.00",
            billing_label="once-off",
            features=["Past-paper revision", "Exam preparation"],
            is_published=True,
        )
        self.faq = FAQ.objects.create(
            question="How do calculus lessons work?",
            answer="Students receive structured calculus guidance and exam-style practice.",
            category="Courses",
            is_published=True,
        )
        FAQ.objects.create(
            question="Private unpublished calculus answer",
            answer="This content must never be included in automatic replies.",
            category="Internal",
            is_published=False,
        )

    def _enquiry(self, *, subject="Course guidance", message="I need calculus course fees and Grade 12 help"):
        return ContactEnquiry.objects.create(
            name="Test Student",
            email="student@example.com",
            subject=subject,
            message=message,
        )

    def test_context_uses_only_relevant_published_website_content(self):
        enquiry = self._enquiry()

        context = build_enquiry_reply_context(enquiry)
        titles = {item.title for item in context["matched_items"]}

        self.assertTrue(context["has_answer"])
        self.assertIn(self.course.title, titles)
        self.assertNotIn("Private unpublished calculus answer", titles)
        self.assertEqual(context["website_url"], "https://example.com")

    def test_no_match_returns_safe_acknowledgement_context(self):
        enquiry = self._enquiry(
            subject="Other",
            message="Please contact me about qzxvplmn unrelated matter",
        )

        context = build_enquiry_reply_context(enquiry)

        self.assertFalse(context["has_answer"])
        self.assertEqual(context["matched_items"], [])

    @patch.dict(
        os.environ,
        {
            "CONTACT_AUTO_REPLY_ENABLED": "true",
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "DEFAULT_FROM_EMAIL": "support@example.com",
        },
        clear=False,
    )
    def test_task_sends_text_and_html_email_without_external_services(self):
        enquiry = self._enquiry()

        result = send_contact_enquiry_auto_reply.run(enquiry.id)

        self.assertEqual(result, {"status": "sent"})
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["student@example.com"])
        self.assertEqual(message.reply_to, ["support@example.com"])
        self.assertIn("Amaris Mathematics Academy", message.subject)
        self.assertIn("Grade 12 Calculus Mastery", message.body)
        self.assertEqual(len(message.alternatives), 1)
        self.assertEqual(message.alternatives[0].mimetype, "text/html")
        self.assertIn("Grade 12 Calculus Mastery", message.alternatives[0].content)

    @patch.dict(
        os.environ,
        {
            "CONTACT_AUTO_REPLY_ENABLED": "true",
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "DEFAULT_FROM_EMAIL": "support@example.com",
        },
        clear=False,
    )
    def test_task_is_idempotent_and_does_not_send_duplicate_reply(self):
        enquiry = self._enquiry()

        first = send_contact_enquiry_auto_reply.run(enquiry.id)
        second = send_contact_enquiry_auto_reply.run(enquiry.id)

        self.assertEqual(first, {"status": "sent"})
        self.assertEqual(second, {"status": "already-sent"})
        self.assertEqual(len(mail.outbox), 1)

    @patch.dict(os.environ, {"CONTACT_AUTO_REPLY_ENABLED": "false"}, clear=False)
    def test_task_can_be_disabled(self):
        enquiry = self._enquiry()

        result = send_contact_enquiry_auto_reply.run(enquiry.id)

        self.assertEqual(result, {"status": "disabled"})
        self.assertEqual(len(mail.outbox), 0)

    def test_new_enquiry_is_queued_only_after_transaction_commit(self):
        with patch("content.tasks.send_contact_enquiry_auto_reply.delay") as delay:
            with self.captureOnCommitCallbacks(execute=True):
                enquiry = self._enquiry()

        delay.assert_called_once_with(enquiry.id)

import os
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase

from content.models import ContactEnquiry, FAQ, SiteSettings
from content.services.enquiry_autoreply import (
    build_enquiry_reply_context,
    generate_enquiry_ai_reply,
)
from content.tasks import send_contact_enquiry_auto_reply


class OpenAIContactAutoReplyTests(TestCase):
    def setUp(self):
        self.site = SiteSettings.objects.create(
            site_name="Amaris Mathematics Academy",
            email="support@amaris.example",
            phone="012 555 0100",
            website_url="https://amaris.example",
            business_hours="Mon-Sun, 07:00-20:00",
        )
        FAQ.objects.create(
            question="Do you support Grade 12 matric Mathematics?",
            answer=("Yes. Published Grade 12 Mathematics support is available through " "Amaris."),
            category="Grade 12",
            is_published=True,
        )
        self.enquiry = ContactEnquiry.objects.create(
            name="Synthetic Student",
            email="student@example.test",
            phone="0710000000",
            subject="Grade 12 matric Mathematics",
            message=("Please tell me about your Grade 12 matric Mathematics support " "options."),
        )
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_generate_reply_uses_responses_api_without_storing_and_omits_contact_fields(
        self,
    ):
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(
            output_text="We provide published Grade 12 Mathematics support."
        )
        context = build_enquiry_reply_context(self.enquiry)

        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-openai-key-not-real",
                "OPENAI_CONTACT_MODEL": "gpt-5.6-luna",
            },
            clear=False,
        ):
            result = generate_enquiry_ai_reply(self.enquiry, context, client=client)

        self.assertEqual(result, "We provide published Grade 12 Mathematics support.")
        call = client.responses.create.call_args.kwargs
        self.assertEqual(call["model"], "gpt-5.6-luna")
        self.assertFalse(call["store"])
        self.assertIn("Grade 12 matric Mathematics", call["input"])
        self.assertIn("published Grade 12 Mathematics support", call["input"])
        self.assertIn("support@amaris.example", call["input"])
        self.assertNotIn(self.enquiry.email, call["input"])
        self.assertNotIn(self.enquiry.phone, call["input"])
        self.assertIn("Use ONLY facts", call["instructions"])

    def test_missing_openai_key_fails_closed(self):
        context = build_enquiry_reply_context(self.enquiry)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(ImproperlyConfigured):
                generate_enquiry_ai_reply(self.enquiry, context, client=Mock())

    def test_task_sends_mocked_gpt_reply_without_external_api_call(self):
        generated_reply = (
            "Amaris provides published Grade 12 Mathematics support. "
            "Please use the website details below for the current options."
        )
        env = {
            "CONTACT_AUTO_REPLY_ENABLED": "true",
            "EMAIL_BACKEND": "django.core.mail.backends.locmem.EmailBackend",
            "DEFAULT_FROM_EMAIL": "noreply@amaris.example",
            "OPENAI_API_KEY": "test-openai-key-not-real",
        }

        with (
            patch.dict(os.environ, env, clear=False),
            patch("content.tasks.generate_enquiry_ai_reply", return_value=generated_reply) as generate_reply,
        ):
            result = send_contact_enquiry_auto_reply.run(self.enquiry.pk)

        self.assertEqual(result, {"status": "sent"})
        generate_reply.assert_called_once()
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.enquiry.email])
        self.assertIn(generated_reply, message.body)
        self.assertIn("Re: Grade 12 matric Mathematics", message.subject)
        self.assertTrue(message.alternatives)
        self.assertIn(generated_reply, message.alternatives[0].content)

    def test_unpublished_website_content_is_not_sent_to_openai(self):
        FAQ.objects.create(
            question="Private draft scholarship",
            answer="This draft must never be used in student replies.",
            category="Draft",
            is_published=False,
        )
        client = Mock()
        client.responses.create.return_value = SimpleNamespace(output_text="Published answer only.")
        context = build_enquiry_reply_context(self.enquiry)

        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-openai-key-not-real"},
            clear=False,
        ):
            generate_enquiry_ai_reply(self.enquiry, context, client=client)

        prompt = client.responses.create.call_args.kwargs["input"]
        self.assertNotIn("Private draft scholarship", prompt)
        self.assertNotIn("This draft must never be used", prompt)

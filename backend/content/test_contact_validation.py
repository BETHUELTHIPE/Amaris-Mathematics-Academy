from django.test import SimpleTestCase

from content.serializers import ContactEnquirySerializer


class ContactRequiredFieldTests(SimpleTestCase):
    payload = {
        "name": "Synthetic Student",
        "email": "synthetic@example.test",
        "phone": "+27 71 000 0000",
        "subject": "technical support",
        "message": "Please help me find the correct course for my level.",
    }
    prompts = {
        "name": "Please enter your full name.",
        "email": "Please enter your email address.",
        "phone": "Please enter your phone number.",
        "subject": "Please choose an enquiry type.",
        "message": "Please enter your message.",
    }

    def test_missing_blank_null_and_whitespace_each_get_the_specific_prompt(self):
        for field, prompt in self.prompts.items():
            for value in (None, "", "   ", "\t\n", "missing"):
                with self.subTest(field=field, value=value):
                    data = {**self.payload, field: value}
                    if value == "missing":
                        del data[field]
                    serializer = ContactEnquirySerializer(data=data)
                    self.assertFalse(serializer.is_valid())
                    self.assertEqual(str(serializer.errors[field][0]), prompt)

    def test_empty_submission_identifies_every_missing_api_field(self):
        serializer = ContactEnquirySerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertEqual(set(serializer.errors), set(self.prompts))

    def test_complete_submission_accepts_trimmed_international_phone(self):
        serializer = ContactEnquirySerializer(data={k: f"  {v}  " for k, v in self.payload.items()})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["phone"], self.payload["phone"])

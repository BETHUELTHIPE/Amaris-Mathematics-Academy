from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from content.locations import COUNTRY_NAMES, country_data, normalize_location
from content.models import ContactEnquiry
from content.serializers import ContactEnquirySerializer
from content.tutor_application_views import ApplicationInput


class LocationValidationTests(SimpleTestCase):
    location = {"country": "ZA", "province": "Gauteng", "city": "Pretoria"}

    def test_country_coverage_and_consistent_city_choices(self):
        self.assertEqual(len(COUNTRY_NAMES), 58)
        self.assertNotIn("US", COUNTRY_NAMES)
        self.assertEqual(len(country_data("ZA")["provinces"]), 9)
        self.assertEqual(normalize_location(self.location.copy()), self.location)

    def test_missing_whitespace_and_inconsistent_choices_are_rejected(self):
        from rest_framework.exceptions import ValidationError

        for field in self.location:
            for value in ("", "   "):
                with self.subTest(field=field, value=value), self.assertRaises(ValidationError) as error:
                    normalize_location({**self.location, field: value})
                self.assertIn(field, error.exception.detail)
        for changes, field in (
            ({"country": "US"}, "country"),
            ({"province": "Western Cape"}, "city"),
            ({"country": "KE"}, "province"),
        ):
            with self.subTest(changes=changes), self.assertRaises(ValidationError) as error:
                normalize_location({**self.location, **changes})
            self.assertIn(field, error.exception.detail)

    def test_explicit_other_selection_requires_names_and_normalizes_them(self):
        value = normalize_location(
            {
                "country": "ZA",
                "province": "__other__",
                "provinceOther": " Synthetic region ",
                "city": "__other__",
                "cityOther": " Synthetic town ",
            }
        )
        self.assertEqual(value, {"country": "ZA", "province": "Synthetic region", "city": "Synthetic town"})
        from rest_framework.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            normalize_location({"country": "ZA", "province": "Gauteng", "city": "__other__", "cityOther": "   "})

    def test_application_keeps_distinct_fields_and_a_readable_legacy_summary(self):
        data = {
            **self.location,
            "full_name": "Synthetic Applicant",
            "phone": "0710000000",
            "qualification": "BSc Mathematics",
            "institution": "Synthetic University",
            "subjects": "Mathematics",
            "programmes": ["caps"],
            "levels": "Grade 12",
            "experience_years": 1,
            "teaching_experience": "Synthetic tutoring experience.",
            "availability": "Weekday evenings with Zoom.",
            "motivation": "I want to help students learn mathematics.",
            "consent": True,
            "documents": [SimpleUploadedFile("synthetic.pdf", b"%PDF-test")],
        }
        serializer = ApplicationInput(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["city"], "Pretoria")
        self.assertEqual(serializer.validated_data["location"], "Pretoria, Gauteng, South Africa")


class ContactLocationPersistenceTests(TestCase):
    @patch("content.serializers.auto_reply_to_enquiry")
    def test_separate_fields_survive_contact_storage(self, reply):
        data = {
            "name": "Synthetic Student",
            "email": "synthetic@example.test",
            "phone": "0710000000",
            "subject": "Course guidance",
            "message": "Please help me choose my next mathematics course.",
            "country": "ZA",
            "province": "Gauteng",
            "city": "Pretoria",
        }
        serializer = ContactEnquirySerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        record = serializer.save()
        record.refresh_from_db()
        self.assertEqual((record.city, record.province, record.country), ("Pretoria", "Gauteng", "ZA"))
        reply.assert_called_once_with(record)

    def test_legacy_records_and_clients_remain_compatible(self):
        record = ContactEnquiry.objects.create(
            name="Legacy Synthetic",
            email="legacy@example.test",
            subject="Legacy",
            message="Historical synthetic record.",
        )
        self.assertEqual((record.city, record.province, record.country), ("", "", ""))
        serializer = ContactEnquirySerializer(
            data={
                "name": "Legacy Synthetic",
                "email": "legacy@example.test",
                "phone": "0710000000",
                "subject": "Legacy",
                "message": "A legacy client can still provide its enquiry details.",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

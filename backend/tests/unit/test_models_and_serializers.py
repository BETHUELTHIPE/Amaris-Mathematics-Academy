from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from content.models import Course, CourseCategory, Testimonial, VideoAsset
from content.serializers import ContactEnquirySerializer


class ModelUnitTests(TestCase):
    def setUp(self):
        self.category = CourseCategory.objects.create(name="CAPS", slug="caps")

    def test_course_save_syncs_publish_flag_with_status(self):
        course = Course.objects.create(
            category=self.category,
            title="Algebra",
            slug="algebra",
            short_description="Algebra",
            description="Algebra course",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
        )
        self.assertTrue(course.is_published)

        course.status = Course.Status.ARCHIVED
        course.save()
        course.refresh_from_db()
        self.assertFalse(course.is_published)

    def test_publishable_model_is_live_obeys_publish_at(self):
        course = Course.objects.create(
            category=self.category,
            title="Calculus",
            slug="calculus",
            short_description="Calculus",
            description="Calculus course",
            curriculum="CAPS",
            academic_level="Grade 12",
            price=950,
            status=Course.Status.PUBLISHED,
            publish_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(course.is_live)

        course.publish_at = timezone.now() - timedelta(seconds=1)
        self.assertTrue(course.is_live)

    def test_video_asset_extracts_youtube_id(self):
        video = VideoAsset(
            title="Limits lesson",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_url="https://www.youtube.com/watch?v=abc123XYZ",
        )
        video.full_clean()
        self.assertEqual(video.youtube_video_id, "abc123XYZ")

    def test_video_asset_rejects_invalid_youtube_url(self):
        video = VideoAsset(
            title="Bad URL",
            provider=VideoAsset.Provider.YOUTUBE,
            youtube_url="https://www.youtube.com/watch",
        )
        with self.assertRaises(ValidationError):
            video.full_clean()

    def test_testimonial_rating_cannot_exceed_five(self):
        testimonial = Testimonial(student_name="Student", quote="Helpful", rating=6)
        with self.assertRaises(ValidationError):
            testimonial.full_clean()


class SerializerUnitTests(TestCase):
    def test_contact_enquiry_requires_minimum_message_length(self):
        serializer = ContactEnquirySerializer(
            data={
                "name": "Test Student",
                "email": "student@example.com",
                "phone": "0710000000",
                "subject": "Course question",
                "message": "Too short",
            }
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("message", serializer.errors)

    def test_contact_enquiry_trims_supported_fields(self):
        serializer = ContactEnquirySerializer(
            data={
                "name": "  Test Student  ",
                "email": "student@example.com",
                "phone": "",
                "subject": "  Course question  ",
                "message": "  This message is long enough for validation.  ",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["name"], "Test Student")
        self.assertEqual(serializer.validated_data["subject"], "Course question")
        self.assertEqual(
            serializer.validated_data["message"],
            "This message is long enough for validation.",
        )

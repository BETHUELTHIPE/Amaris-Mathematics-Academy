from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    FAQ,
    Announcement,
    ContactEnquiry,
    Course,
    CourseCategory,
    CourseModule,
    Lesson,
    NavigationItem,
    Page,
    PageSection,
    PricingPlan,
    SiteSettings,
    Testimonial,
)


class AbsoluteFileMixin:
    def file_url(self, field) -> str | None:
        if not field:
            return None
        try:
            url = field.url
        except (ValueError, AttributeError):
            return None
        request = self.context.get("request")
        return request.build_absolute_uri(url) if request and url.startswith("/") else url


class SiteSettingsSerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    favicon_url = serializers.SerializerMethodField()

    class Meta:
        model = SiteSettings
        exclude = ("created_at", "updated_at", "maintenance_mode")

    @extend_schema_field(OpenApiTypes.URI)
    def get_logo_url(self, obj) -> str | None:
        return self.file_url(obj.logo)

    @extend_schema_field(OpenApiTypes.URI)
    def get_favicon_url(self, obj) -> str | None:
        return self.file_url(obj.favicon)


class NavigationItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = NavigationItem
        fields = ("id", "label", "url", "location", "order", "open_in_new_tab")


class PageSectionSerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = PageSection
        fields = (
            "id",
            "section_key",
            "eyebrow",
            "heading",
            "body",
            "image_url",
            "call_to_action_label",
            "call_to_action_url",
            "content",
            "order",
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_image_url(self, obj) -> str | None:
        return self.file_url(obj.image)


class PageSerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    hero_image_url = serializers.SerializerMethodField()
    sections = serializers.SerializerMethodField()

    class Meta:
        model = Page
        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "hero_image_url",
            "meta_title",
            "meta_description",
            "template_key",
            "sections",
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_hero_image_url(self, obj) -> str | None:
        return self.file_url(obj.hero_image)

    @extend_schema_field(PageSectionSerializer(many=True))
    def get_sections(self, obj) -> list[dict]:
        sections = [section for section in obj.sections.all() if section.is_live]
        return PageSectionSerializer(sections, many=True, context=self.context).data


class CourseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = CourseCategory
        fields = ("id", "name", "slug", "description", "order")


class LessonSummarySerializer(serializers.ModelSerializer):
    has_video = serializers.SerializerMethodField()

    class Meta:
        model = Lesson
        fields = (
            "id",
            "title",
            "slug",
            "summary",
            "duration_minutes",
            "order",
            "is_free_preview",
            "has_video",
        )

    @extend_schema_field(OpenApiTypes.BOOL)
    def get_has_video(self, obj) -> bool:
        return obj.video_id is not None


class CourseModuleSerializer(serializers.ModelSerializer):
    lessons = serializers.SerializerMethodField()

    class Meta:
        model = CourseModule
        fields = ("id", "title", "description", "order", "lessons")

    @extend_schema_field(LessonSummarySerializer(many=True))
    def get_lessons(self, obj) -> list[dict]:
        lessons = [lesson for lesson in obj.lessons.all() if lesson.is_live]
        return LessonSummarySerializer(lessons, many=True, context=self.context).data


class CourseSerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    modules = serializers.SerializerMethodField()
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "category",
            "title",
            "slug",
            "short_description",
            "description",
            "curriculum",
            "academic_level",
            "price",
            "compare_at_price",
            "cover_image_url",
            "outcomes",
            "estimated_hours",
            "featured",
            "lesson_count",
            "modules",
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_cover_image_url(self, obj) -> str | None:
        return self.file_url(obj.cover_image)

    @extend_schema_field(CourseModuleSerializer(many=True))
    def get_modules(self, obj) -> list[dict]:
        modules = [module for module in obj.modules.all() if module.is_published]
        return CourseModuleSerializer(modules, many=True, context=self.context).data


class CourseSummarySerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    category = CourseCategorySerializer(read_only=True)
    cover_image_url = serializers.SerializerMethodField()
    lesson_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Course
        fields = (
            "id",
            "category",
            "title",
            "slug",
            "short_description",
            "curriculum",
            "academic_level",
            "price",
            "compare_at_price",
            "cover_image_url",
            "estimated_hours",
            "featured",
            "lesson_count",
        )

    @extend_schema_field(OpenApiTypes.URI)
    def get_cover_image_url(self, obj) -> str | None:
        return self.file_url(obj.cover_image)


class PricingPlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingPlan
        exclude = ("created_at", "updated_at", "is_published", "publish_at")


class TestimonialSerializer(AbsoluteFileMixin, serializers.ModelSerializer):
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Testimonial
        fields = ("id", "student_name", "student_context", "quote", "photo_url", "rating", "order")

    @extend_schema_field(OpenApiTypes.URI)
    def get_photo_url(self, obj) -> str | None:
        return self.file_url(obj.photo)


class FAQSerializer(serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ("id", "question", "answer", "category", "order")


class AnnouncementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ("id", "title", "message", "link_label", "link_url", "priority", "expires_at")


class ContactEnquirySerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactEnquiry
        fields = ("name", "email", "phone", "subject", "message")
        extra_kwargs = {
            "name": {"trim_whitespace": True},
            "subject": {"trim_whitespace": True},
            "message": {"trim_whitespace": True},
        }

    def validate_message(self, value):
        if len(value) < 20:
            raise serializers.ValidationError("Please provide at least 20 characters.")
        return value


class SiteBootstrapSerializer(serializers.Serializer):
    settings = SiteSettingsSerializer(allow_null=True)
    navigation = NavigationItemSerializer(many=True)
    announcements = AnnouncementSerializer(many=True)

from datetime import timedelta

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from content.models import SiteSettings
from content.performance_models import PerformanceDigest, PerformanceSchedule
from content.services.performance_metrics import SAST, build_snapshot
from content.services.performance_reports import archived_pdf


class PrivatePerformanceAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        user = request.user
        return bool(
            user.is_active
            and (
                user.is_superuser
                or (
                    user.is_staff
                    and not user.groups.filter(name="Tutors").exists()
                    and user.has_perm("content.view_performancedigest")
                )
            )
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields)


@admin.register(PerformanceSchedule)
class PerformanceScheduleAdmin(PrivatePerformanceAdmin):
    list_display = ("payment_mode", "anchor_date", "created_at")


@admin.register(PerformanceDigest)
class PerformanceDigestAdmin(PrivatePerformanceAdmin):
    list_display = ("period_start", "period_end", "payment_mode", "delivery_status", "sent_at", "open_dashboard")
    list_filter = ("payment_mode", "delivery_status")
    change_list_template = "admin/content/performancedigest/change_list.html"
    exclude = ("pdf", "snapshot")

    def get_readonly_fields(self, request, obj=None):
        return tuple(field.name for field in self.model._meta.fields if field.name not in self.exclude) + (
            "open_dashboard",
        )

    def get_urls(self):
        return [
            path("dashboard/", self.admin_site.admin_view(self.dashboard), name="content_performancedigest_dashboard"),
            path(
                "<uuid:report_id>/pdf/", self.admin_site.admin_view(self.download), name="content_performancedigest_pdf"
            ),
        ] + super().get_urls()

    @admin.display(description="Performance dashboard")
    def open_dashboard(self, obj):
        url = reverse("admin:content_performancedigest_dashboard")
        return format_html('<a href="{}?report={}">View rankings and insights</a>', url, obj.pk)

    def dashboard(self, request):
        if not self.has_view_permission(request):
            raise PermissionDenied
        item = None
        preview = request.GET.get("preview") == "1"
        mode = settings.ADMIN_PERFORMANCE_PAYMENT_MODE
        if preview:
            end = timezone.now().astimezone(SAST).date()
            snapshot = build_snapshot(end - timedelta(days=14), end, mode)
        else:
            report_id = request.GET.get("report")
            try:
                item = (
                    PerformanceDigest.objects.get(pk=report_id)
                    if report_id
                    else PerformanceDigest.objects.filter(payment_mode=mode).first()
                )
            except (PerformanceDigest.DoesNotExist, ValidationError) as exc:
                raise Http404 from exc
            snapshot = item.snapshot if item else None
        schedule = PerformanceSchedule.objects.filter(payment_mode=mode).first()
        response = TemplateResponse(
            request,
            "admin/content/performancedigest/dashboard.html",
            {
                **self.admin_site.each_context(request),
                "title": "Academy performance review",
                "opts": self.model._meta,
                "report": item,
                "data": snapshot,
                "preview": preview,
                "site": SiteSettings.objects.first() or SiteSettings(),
                "enabled": settings.ADMIN_PERFORMANCE_REPORTS_ENABLED,
                "mode": mode,
                "first_due": schedule.anchor_date + timedelta(days=14) if schedule else None,
            },
        )
        response["Cache-Control"] = "private, no-store"
        return response

    def download(self, request, report_id):
        if not self.has_view_permission(request):
            raise PermissionDenied
        try:
            item = PerformanceDigest.objects.get(pk=report_id)
        except PerformanceDigest.DoesNotExist as exc:
            raise Http404 from exc
        try:
            document = archived_pdf(item)
        except (ValidationError, OSError, BotoCoreError, ClientError):
            return HttpResponse(
                "The private archive needs review.", status=503, headers={"Cache-Control": "private, no-store"}
            )
        response = HttpResponse(document, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="amaris-performance-{item.period_start}.pdf"'
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response

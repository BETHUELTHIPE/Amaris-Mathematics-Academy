"""Organize only the model links Django has already authorized for this user."""

from django import template

register = template.Library()

GROUPS = (
    ("learning", "Learning & courses", "Courses, lessons and learning resources", "fa-book-open"),
    ("people", "Students & tutors", "Learner records and tutor applications", "fa-user-graduate"),
    ("bookings", "Bookings & requests", "Class schedules and service requests", "fa-calendar-alt"),
    ("finance", "Payments & finance", "Invoices, payments and tutor earnings", "fa-wallet"),
    ("content", "Website & content", "Keep your academy website up to date", "fa-layer-group"),
    ("admin", "Administration", "Accounts, groups and access permissions", "fa-shield-alt"),
    ("operations", "Operations", "Private monitoring and service consoles", "fa-chart-line"),
)
MODEL_GROUPS = {
    **dict.fromkeys(("Course", "CourseCategory", "CourseModule", "Lesson", "VideoAsset", "ResourceAsset"), "learning"),
    **dict.fromkeys(
        ("StudentRecord", "Enrollment", "TutorApplication", "TutorApplicationDocument", "TutorContract"), "people"
    ),
    **dict.fromkeys(
        ("LiveClassBooking", "TutorAvailabilitySlot", "VideoRequest", "VideoRequestDocument", "ServiceTicket"),
        "bookings",
    ),
    **dict.fromkeys(
        (
            "Payment",
            "Invoice",
            "PaymentWebhookEvent",
            "PaymentReconciliationRun",
            "TutorEarning",
            "TutorPaymentProfile",
            "TutorPayout",
            "TutorPayoutItem",
            "TutorCourseAssignment",
        ),
        "finance",
    ),
}


@register.simple_tag
def academy_workspace(app_list):
    groups = {
        key: {"key": key, "title": title, "description": description, "icon": icon, "models": []}
        for key, title, description, icon in GROUPS
    }
    shortcuts = []
    choices = {
        "LiveClassBooking": "Review bookings",
        "TutorApplication": "Tutor applications",
        "Payment": "Review payments",
    }
    for app in app_list:
        for model in app["models"]:
            if not model.get("admin_url"):
                continue
            if app["app_label"] == "monitoring":
                key = "operations"
            elif app["app_label"] != "content":
                key = "admin"
            else:
                key = MODEL_GROUPS.get(model["object_name"], "content")
            groups[key]["models"].append(model)
            if app["app_label"] == "content" and model["object_name"] in choices:
                shortcuts.append(
                    {"label": choices[model["object_name"]], "url": model["admin_url"], "icon": groups[key]["icon"]}
                )
    visible = [group for group in groups.values() if group["models"]]
    return {"groups": visible, "shortcuts": shortcuts, "tool_count": sum(len(group["models"]) for group in visible)}

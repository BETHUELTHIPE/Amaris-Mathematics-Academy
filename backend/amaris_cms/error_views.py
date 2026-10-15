from dataclasses import dataclass

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


@dataclass(frozen=True)
class ErrorContent:
    eyebrow: str
    title: str
    message: str
    next_step: str
    action_label: str
    action_url: str


ERROR_CONTENT = {
    400: ErrorContent(
        "Request not understood",
        "Let’s try that again.",
        "We could not safely process the request.",
        "Check the information you entered, then return and try once more.",
        "Return to the website",
        "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site/",
    ),
    403: ErrorContent(
        "Access restricted",
        "You do not have access to this page.",
        "This area requires the correct account or staff permission.",
        "Sign in with an authorised account or contact support if you believe this is incorrect.",
        "Go to secure sign-in",
        "/admin/login/",
    ),
    404: ErrorContent(
        "Page not found",
        "That page could not be found.",
        "The address may be outdated, mistyped, or the page may have moved.",
        "Return to the administration home or open the public academy website.",
        "Administration home",
        "/admin/",
    ),
    429: ErrorContent(
        "Please slow down",
        "Too many attempts were made.",
        "New attempts are temporarily paused to protect the academy.",
        "Wait a few minutes, then try once. Repeated attempts will not shorten the wait.",
        "Return to the website",
        "https://amaris-mathematics-academy.bethuelthipe.chatgpt.site/",
    ),
    500: ErrorContent(
        "Something went wrong",
        "We could not complete that action.",
        "The administration service encountered an unexpected problem.",
        "Try again once. If the problem continues, send the support reference below to the academy team.",
        "Administration home",
        "/admin/",
    ),
}


def _render_error(request: HttpRequest, status: int) -> HttpResponse:
    content = ERROR_CONTENT[status]
    return render(
        request,
        "errors/status.html",
        {
            "status_code": status,
            "content": content,
            "correlation_reference": getattr(request, "correlation_reference", "AMR-SUPPORT-REFERENCE"),
        },
        status=status,
    )


def error_400(request, exception=None):
    return _render_error(request, 400)


def error_403(request, exception=None, reason=""):
    return _render_error(request, 403)


def error_404(request, exception=None):
    return _render_error(request, 404)


def error_429(request, exception=None):
    return _render_error(request, 429)


def error_500(request):
    return _render_error(request, 500)

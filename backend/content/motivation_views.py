import uuid

from django.core import signing
from django.http import HttpResponse, HttpResponseBadRequest
from django.middleware.csrf import get_token
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import StudentMotivationEmail
from .services.student_motivation import TOKEN_SALT


@never_cache
@require_http_methods(["GET", "POST"])
def unsubscribe(request):
    try:
        user_id = uuid.UUID(signing.loads(request.GET.get("token", ""), salt=TOKEN_SALT))
    except (signing.BadSignature, ValueError, TypeError):
        return HttpResponseBadRequest("This unsubscribe link is invalid.")
    if request.method == "POST":
        StudentMotivationEmail.objects.filter(supabase_user_id=user_id).update(unsubscribed_at=timezone.now())
        content = format_html(
            "<h1>{}</h1><p>{}</p>",
            "You are unsubscribed",
            "You will no longer receive motivational emails from Amaris.",
        )
    else:
        content = format_html(
            "<h1>Motivational email preferences</h1><p>Stop receiving motivational emails from Amaris.</p>"
            '<form method="post"><input type="hidden" name="csrfmiddlewaretoken" value="{}">'
            '<button type="submit">Unsubscribe</button></form>',
            get_token(request),
        )
    response = HttpResponse(
        format_html(
            '<!doctype html><html lang="en"><title>Amaris email preferences</title>'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<body>{}</body></html>",
            content,
        )
    )
    response["Referrer-Policy"] = "same-origin"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response

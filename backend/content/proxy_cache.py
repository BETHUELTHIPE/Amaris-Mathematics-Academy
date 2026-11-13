"""Explicit shared-cache permission for the two anonymous public JSON endpoints."""

from functools import wraps
from time import time

from django.utils.cache import get_max_age, patch_cache_control
from django.utils.http import parse_http_date_safe


def public_proxy_cache(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        response = view(request, *args, **kwargs)
        if request.method not in {"GET", "HEAD"} or request.COOKIES or request.headers.get("Authorization"):
            return response

        def mark_public(result):
            directives = {part.partition("=")[0].strip().lower() for part in result.get("Cache-Control", "").split(",")}
            if (
                result.status_code == 200
                and not result.cookies
                and not directives.intersection({"private", "no-store", "no-cache"})
                and (get_max_age(result) or 0) > 0
            ):
                # A Redis/cache_page hit can already be old. A second cache
                # must not restart its full TTL or outlive expiring asset URLs.
                now = int(time())
                try:
                    age = max(0, int(result.get("Age", "0")))
                except ValueError:
                    return result
                remaining = (get_max_age(result) or 0) - age
                expires = parse_http_date_safe(result.get("Expires", ""))
                if expires is not None:
                    remaining = min(remaining, expires - now)
                if remaining <= 1 or result.has_header("X-Accel-Expires"):
                    return result
                patch_cache_control(result, public=True, max_age=remaining)
                # Absolute expiry plus a one-second margin avoids TTL renewal
                # and Nginx's whole-second boundary. JSON microcache is <=30s.
                result["X-Accel-Expires"] = "@" + str(min(now + 30, now + remaining - 1))
            return result

        # cache_page adds its TTL when DRF renders. Run after that callback,
        # without removing or overriding an existing privacy/expiry directive.
        if hasattr(response, "add_post_render_callback"):
            response.add_post_render_callback(mark_public)
        else:
            mark_public(response)
        return response

    return wrapped

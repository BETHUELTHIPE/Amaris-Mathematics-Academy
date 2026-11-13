"""Explicit shared-cache permission for the two anonymous public JSON endpoints."""

from functools import wraps

from django.utils.cache import get_max_age, patch_cache_control


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
                patch_cache_control(result, public=True)
            return result

        # cache_page adds its TTL when DRF renders. Run after that callback,
        # without removing or overriding an existing privacy/expiry directive.
        if hasattr(response, "add_post_render_callback"):
            response.add_post_render_callback(mark_public)
        else:
            mark_public(response)
        return response

    return wrapped

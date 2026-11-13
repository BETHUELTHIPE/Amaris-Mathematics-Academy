from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase
from django.utils.cache import patch_response_headers
from django.utils.http import http_date
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from content.proxy_cache import public_proxy_cache


class PublicProxyCacheTests(SimpleTestCase):
    def check(self, *, control="max-age=60", status=200, cookie=False, **headers):
        response = HttpResponse("public data", status=status, headers={"Cache-Control": control})
        if cookie:
            response.set_cookie("session", "synthetic")
        request = RequestFactory().get("/api/v1/courses/", **headers)
        return public_proxy_cache(lambda request: response)(request)

    def test_anonymous_positive_ttl_response_explicitly_allows_shared_caching(self):
        self.assertIn("public", self.check()["Cache-Control"])

    def test_privacy_directives_and_expiry_are_never_overridden(self):
        for control in ("private, max-age=60", "no-store, max-age=60", "no-cache, max-age=60", "max-age=0", ""):
            self.assertEqual(self.check(control=control)["Cache-Control"], control)

    def test_authenticated_cookie_and_cookie_setting_responses_remain_unchanged(self):
        for headers in (
            {"HTTP_COOKIE": "session=synthetic"},
            {"HTTP_AUTHORIZATION": "Bearer synthetic"},
            {"cookie": True},
        ):
            self.assertNotIn("public", self.check(**headers)["Cache-Control"])

    def test_errors_are_not_opted_into_shared_caching(self):
        self.assertNotIn("public", self.check(status=503)["Cache-Control"])

    def test_drf_opt_in_runs_after_cache_page_render_time_ttl(self):
        response = Response({"public": "course catalogue"})
        response.accepted_renderer = JSONRenderer()
        response.accepted_media_type = "application/json"
        response.renderer_context = {}
        response.add_post_render_callback(lambda result: patch_response_headers(result, cache_timeout=60))
        public_proxy_cache(lambda request, result=response: result)(RequestFactory().get("/api/v1/courses/"))
        response.render()
        self.assertIn("public", response["Cache-Control"])

    def test_aged_django_response_never_gets_a_fresh_full_ttl(self):
        response = HttpResponse(
            "public", headers={"Cache-Control": "max-age=300", "Age": "290", "Expires": http_date(1300)}
        )
        with patch("content.proxy_cache.time", return_value=1290):
            public_proxy_cache(lambda request, result=response: result)(RequestFactory().get("/api/v1/courses/"))
        self.assertIn("max-age=10", response["Cache-Control"])
        self.assertEqual(response["X-Accel-Expires"], "@1299")
        self.assertEqual(response["Age"], "290")

    def test_expired_or_malformed_age_response_is_not_opted_in(self):
        for age in ("300", "not-a-number"):
            response = HttpResponse("public", headers={"Cache-Control": "max-age=300", "Age": age})
            result = public_proxy_cache(lambda request, result=response: result)(
                RequestFactory().get("/api/v1/courses/")
            )
            self.assertNotIn("public", result["Cache-Control"])
            self.assertFalse(result.has_header("X-Accel-Expires"))

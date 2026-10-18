import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from content.models import WebVitalSample


@override_settings(
    WEB_VITALS_INGEST_TOKEN="x" * 48,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AnonymousWebVitalsTests(TestCase):
    def send(self, data=None, token="x" * 48):
        return self.client.post(
            reverse("web-vitals-ingest"),
            data=json.dumps(
                data
                or {
                    "name": "LCP",
                    "value": 2300.0,
                    "id": "v4-example-metric-id",
                    "page": "courses",
                    "device": "mobile",
                }
            ),
            content_type="application/json",
            HTTP_X_AMARIS_RUM_TOKEN=token,
            secure=True,
        )

    def test_authenticated_internal_sample_is_anonymous_and_idempotent(self):
        response = self.send()
        self.assertEqual(response.status_code, 204)
        self.assertIn("no-store", response["Cache-Control"])
        obj = WebVitalSample.objects.get()
        self.assertEqual(obj.page_group, "courses")
        self.assertNotEqual(obj.event_hash, "v4-example-metric-id")

        self.assertEqual(
            self.send(
                {"name": "LCP", "value": 2600.0, "id": "v4-example-metric-id", "page": "courses", "device": "mobile"}
            ).status_code,
            204,
        )
        self.assertEqual(WebVitalSample.objects.count(), 1)
        self.assertEqual(WebVitalSample.objects.get().value, 2600.0)

    def test_fail_closed_with_missing_or_invalid_secret(self):
        self.assertEqual(self.send(token="incorrect").status_code, 403)
        self.assertEqual(WebVitalSample.objects.count(), 0)
        with override_settings(WEB_VITALS_INGEST_TOKEN=""):
            self.assertEqual(self.send().status_code, 503)

    def test_rejects_invalid_metrics_and_freeform_user_data(self):
        payload = {"name": "INP", "value": 160, "id": "v4-example-metric-id", "page": "other", "device": "desktop"}
        bad = [
            dict(payload, name="FID"),
            dict(payload, value=-3),
            dict(payload, value=9999999),
            dict(payload, value=True),
            dict(payload, page="/student/orders/123?token=private"),
            dict(payload, device="Samsung-S24"),
            dict(payload, email="student@example.com"),
            dict(payload, id="u"),
        ]
        for variant in bad:
            with self.subTest(payload=variant):
                self.assertEqual(self.send(variant).status_code, 400)
        self.assertEqual(WebVitalSample.objects.count(), 0)


@override_settings(WEB_VITALS_INGEST_TOKEN="x" * 48)
class WebVitalsReportTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser("rum_super", "root@example.test", "only-for-tests")
        self.staff = User.objects.create_user("rum_staff", "staff@example.test", "only-for-tests", is_staff=True)
        for number in range(1, 21):
            WebVitalSample.objects.create(
                event_hash=f"{number:064x}",
                metric_name="LCP",
                value=float(number),
                page_group="home",
                device="mobile",
            )

    def test_report_is_superuser_only(self):
        uri = reverse("web-vitals-report")
        self.assertEqual(self.client.get(uri, secure=True).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(uri, secure=True).status_code, 403)
        self.client.force_login(self.superuser)
        reply = self.client.get(uri, secure=True)
        self.assertEqual(reply.status_code, 200)
        self.assertIn("no-store", reply["Cache-Control"])
        group = reply.json()["groups"][0]
        self.assertEqual(group["metric"], "LCP")
        self.assertEqual(group["samples"], 20)
        self.assertAlmostEqual(group["p75"], 15.25)
        self.assertEqual(group["status"], "good")

    def test_small_groups_are_not_reported_as_reliable_p75(self):
        WebVitalSample.objects.all().delete()
        WebVitalSample.objects.create(
            event_hash="a" * 64,
            metric_name="CLS",
            value=0.23,
            page_group="home",
            device="mobile",
        )
        self.client.force_login(self.superuser)
        item = self.client.get(reverse("web-vitals-report"), secure=True).json()["groups"][0]
        self.assertIsNone(item["p75"])
        self.assertEqual(item["status"], "insufficient_data")
        self.assertEqual(
            self.client.get(reverse("web-vitals-report"), {"days": "invalid"}, secure=True).status_code, 400
        )


    def test_p75_boundary_is_independent_per_metric_page_and_device(self):
        # An otherwise healthy group must not lend its sample count to a
        # different device, metric or page category.
        for number in range(19):
            WebVitalSample.objects.create(
                event_hash=f"{1000 + number:064x}",
                metric_name="LCP", value=1000,
                page_group="courses", device="mobile",
            )
            WebVitalSample.objects.create(
                event_hash=f"{2000 + number:064x}",
                metric_name="CLS", value=0.04,
                page_group="home", device="mobile",
            )
        for number in range(20):
            WebVitalSample.objects.create(
                event_hash=f"{3000 + number:064x}",
                metric_name="INP", value=180,
                page_group="home", device="desktop",
            )
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("web-vitals-report"), secure=True)
        self.assertEqual(response.status_code, 200)
        groups = {
            (item["metric"], item["page"], item["device"]): item
            for item in response.json()["groups"]
        }
        self.assertEqual(len(groups), 4)
        self.assertEqual(groups[("LCP", "home", "mobile")]["samples"], 20)
        self.assertIsNotNone(groups[("LCP", "home", "mobile")]["p75"])
        self.assertEqual(groups[("INP", "home", "desktop")]["samples"], 20)
        self.assertIsNotNone(groups[("INP", "home", "desktop")]["p75"])
        for category in (("LCP", "courses", "mobile"), ("CLS", "home", "mobile")):
            self.assertEqual(groups[category]["samples"], 19)
            self.assertIsNone(groups[category]["p75"])
            self.assertEqual(groups[category]["status"], "insufficient_data")

    @override_settings(
        STORAGES={
            "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
        }
    )
    def test_admin_changelist_embeds_only_superuser_summary_and_static_script(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:content_webvitalsample_changelist"), secure=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="amaris-web-vitals-dashboard"')
        self.assertContains(response, "content/web_vitals_admin.js")
        self.assertContains(response, "at least 20 valid samples")
        self.assertContains(response, 'value="28"')

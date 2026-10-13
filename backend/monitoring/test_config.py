import unittest

from .render_config import build_config


class MonitoringConfigTests(unittest.TestCase):
    def test_remote_django_target_preserves_scheme_port_and_metrics_path(self):
        config = build_config(
            "https://cms.example.com:8443/private-metrics",
            "https://cms.example.com:8443/health/ready/",
            "https://students.example.com/",
        )
        django = next(job for job in config["scrape_configs"] if job["job_name"] == "django")
        self.assertEqual(django["scheme"], "https")
        self.assertEqual(django["metrics_path"], "/private-metrics")
        self.assertEqual(django["static_configs"][0]["targets"], ["cms.example.com:8443"])
        self.assertNotIn("web:8000", str(config))

    def test_external_probe_uses_configured_student_site_and_backend(self):
        config = build_config(
            "https://cms.example.com/metrics", "https://cms.example.com/ready", "https://students.example.com/"
        )
        probe = next(job for job in config["scrape_configs"] if job["job_name"] == "blackbox_http")
        self.assertEqual(
            probe["static_configs"][0]["targets"], ["https://students.example.com/", "https://cms.example.com/ready"]
        )
        self.assertEqual(probe["relabel_configs"][-1]["replacement"], "blackbox_exporter:9115")

    def test_rejects_insecure_or_credential_bearing_application_targets(self):
        for invalid in (
            "http://cms.example.com/metrics",
            "https://user:secret@cms.example.com/metrics",
            "https://cms.example.com/metrics?token=secret",
            "https://cms.example.com/metrics#fragment",
        ):
            for index in range(3):
                urls = [
                    "https://cms.example.com/metrics",
                    "https://cms.example.com/ready",
                    "https://students.example.com/",
                ]
                urls[index] = invalid
                with self.subTest(url=invalid, position=index), self.assertRaises(ValueError):
                    build_config(*urls)

"""Render exporter regression tests (no Render API credentials or network calls)."""
import importlib.util
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import requests

os.environ.setdefault("RENDER_API_KEY", "synthetic-test-key")
os.environ.setdefault("RENDER_RESOURCES", "srv-one=backend,srv-two=frontend")
os.environ.setdefault("RENDER_SERVICE_IDS", "srv-one,srv-two")

spec = importlib.util.spec_from_file_location(
    "metrics_exporter", Path(__file__).with_name("exporter.py")
)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def invalid_request():
    response = requests.Response()
    response.status_code = 400
    response.url = "https://api.render.com/v1/metrics/http-latency"
    return requests.HTTPError("400", response=response)


class PartialRefreshTests(unittest.TestCase):
    def test_400_combined_request_falls_back_to_each_service(self):
        def fetch(endpoint, ids, **extra):
            if len(ids) > 1 or ids == ["srv-two"]:
                raise invalid_request()
            return [{"labels": [{"field": "service", "value": "srv-one"}],
                     "values": [{"timestamp": "", "value": 0.12}], "unit": "seconds"}]

        with patch.object(exporter, "_get", side_effect=fetch):
            series, complete = exporter._get_with_partial_recovery(
                "http-latency", ["srv-one", "srv-two"], quantile=0.95
            )
        self.assertEqual(len(series), 1)
        self.assertFalse(complete)

    def test_partial_latency_keeps_valid_cpu_and_does_not_report_full_success(self):
        cpu = [{"labels": [{"field": "resource", "value": "srv-one"}],
                "values": [{"timestamp": "", "value": 0.5}], "unit": "cores"}]
        def fetch(endpoint, ids, **kwargs):
            if endpoint == "http-latency":
                raise invalid_request()
            return cpu if endpoint == "cpu" else []
        with patch.object(exporter, "_get", side_effect=fetch):
            exporter.refresh()
        self.assertEqual(exporter.REFRESH_SUCCESS._value.get(), 0)
        self.assertEqual(exporter.METRIC_REFRESH_SUCCESS.labels("cpu")._value.get(), 1)
        self.assertEqual(exporter.METRIC_REFRESH_SUCCESS.labels("http-latency")._value.get(), 0)
        self.assertEqual(exporter.CPU.labels("srv-one", "backend", "cores")._value.get(), 0.5)


if __name__ == "__main__":
    unittest.main()

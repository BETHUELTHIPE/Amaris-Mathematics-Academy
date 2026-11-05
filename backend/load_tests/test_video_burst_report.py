"""Offline evidence-parser tests; synthetic intervals are not capacity evidence."""

import unittest

from load_tests.video_burst_report import analyse

SHA = "a" * 40


def interval(index, *, begin=10_000, end=10_100, valid=1, status=201):
    return f'level=info msg="VIDEO_SUBMISSION|offline|{SHA}|{index}|{begin}|{end}|{valid}|{status}" source=console'


def report(lines, target=50_000):
    return analyse(lines, target=target, run_id="offline", deployed_sha=SHA, release_at_ms=10_000)


class BurstEvidenceTests(unittest.TestCase):
    def test_50000_overlapping_intervals_pass_client_analysis_without_claiming_server_capacity(self):
        result = report(interval(index) for index in range(1, 50_001))
        self.assertTrue(result["client_burst_gate_passed"])
        self.assertEqual(result["peak_client_inflight"], 50_000)
        self.assertFalse(result["server_capacity_verified"])

    def test_16_submissions_do_not_verify_50000(self):
        result = report(interval(index) for index in range(1, 17))
        self.assertFalse(result["client_burst_gate_passed"])
        self.assertEqual(result["peak_client_inflight"], 16)

    def test_sequential_submissions_do_not_count_as_simultaneous(self):
        result = report([interval(1), interval(2, begin=10_100, end=10_200)], target=2)
        self.assertEqual(result["peak_client_inflight"], 1)
        self.assertFalse(result["client_burst_gate_passed"])

    def test_missing_duplicate_failed_and_wrong_run_evidence_fail(self):
        for lines in (
            [],
            [interval(1), interval(1)],
            [interval(1), interval(2, valid=0)],
            [interval(1), interval(2, status=429)],
            [interval(1), interval(2, status=503)],
            [interval(1).replace("offline", "other"), interval(2)],
            [interval(1), "VIDEO_SUBMISSION|broken"],
            [interval(1), interval(3)],
        ):
            with self.subTest(lines=lines):
                self.assertFalse(report(lines, target=2)["client_burst_gate_passed"])

    def test_latency_and_release_window_are_enforced(self):
        for line in (
            interval(1, begin=9_999),
            interval(1, begin=11_001, end=11_100),
            interval(1, end=12_001),
            interval(1, end=9_999),
        ):
            with self.subTest(line=line):
                self.assertFalse(report([line], target=1)["client_burst_gate_passed"])

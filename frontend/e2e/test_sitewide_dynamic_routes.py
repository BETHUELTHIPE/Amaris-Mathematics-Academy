"""Prevent missing dynamic-route pages from being miscounted as verified."""
import unittest

from sitewide_responsive_audit import DEVICES, DYNAMIC_PUBLIC_FIXTURES, discover


class DynamicRouteCoverageTests(unittest.TestCase):
    def setUp(self):
        self.routes = discover()

    def test_source_backed_positive_and_negative_cases_are_distinct(self):
        for key, fixture in DYNAMIC_PUBLIC_FIXTURES.items():
            matches = [r for r in self.routes if r["source"] == f"app/{key}/page.tsx"]
            positives = [r for r in matches if r["coverage"] == "valid-dynamic"]
            negatives = [r for r in matches if r["coverage"] == "negative-404"]
            self.assertEqual(len(positives), 1, key)
            self.assertEqual(len(negatives), 1, key)
            self.assertEqual(positives[0]["route"], fixture["route"])
            self.assertEqual(positives[0]["expectedHeading"], fixture["heading"])
            self.assertTrue(positives[0]["expectedBodyText"])
            self.assertIn("responsive-test-invalid-slug", negatives[0]["route"])
            self.assertNotEqual(positives[0]["route"], negatives[0]["route"])

    def test_positive_and_expected_404_cannot_be_counted_together(self):
        positives = [r for r in self.routes if r["coverage"] == "valid-dynamic"]
        negative = [r for r in self.routes if r["coverage"] == "negative-404"]
        self.assertEqual(len(positives), 2)
        self.assertEqual(len(negative), 2)
        self.assertEqual(len(positives) * len(DEVICES), 14)
        self.assertEqual(len(negative) * len(DEVICES), 14)

    def test_authenticated_detail_routes_are_not_credited_as_public_pages(self):
        for source in ("app/checkout/[slug]/page.tsx",
                       "app/learn/[courseSlug]/[lessonSlug]/page.tsx"):
            matches = [r for r in self.routes if r["source"] == source]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["coverage"], "protected")
            self.assertTrue(matches[0]["conditional"])


if __name__ == "__main__":
    unittest.main()

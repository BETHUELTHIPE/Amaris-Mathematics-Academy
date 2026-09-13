import json
import random
import tempfile
import unittest
from pathlib import Path

from test_data.factories import ENTITIES, Factory
from test_data.generate import generate


class SyntheticFactoryTests(unittest.TestCase):
    def test_repeated_exports_are_byte_identical(self):
        factory = Factory(students=8, tutors=2, courses=3, lessons_per_course=2)
        with tempfile.TemporaryDirectory() as directory:
            first, second = Path(directory) / "first", Path(directory) / "second"
            generate(factory, first)
            random.seed(9182)
            random.random()
            generate(factory, second)
            for path in first.iterdir():
                self.assertEqual(path.read_bytes(), (second / path.name).read_bytes())
            with self.assertRaises(ValueError):
                generate(factory, first)

    def test_slices_counts_and_seeds(self):
        factory = Factory(students=12)
        for entity in ENTITIES:
            rows = list(factory.rows(entity))
            self.assertEqual(len(rows), factory.counts[entity])
            self.assertEqual(rows, list(factory.rows(entity, 0, 2)) + list(factory.rows(entity, 2)))
            self.assertEqual(len({r["id"] for r in rows}), len(rows))
            self.assertNotEqual(rows[0]["id"], Factory(seed=42).row(entity, 0)["id"])

    def test_relationships_and_financial_consistency(self):
        factory = Factory(students=12, tutors=2, courses=3, lessons_per_course=2)
        data = {entity: {r["id"]: r for r in factory.rows(entity)} for entity in ENTITIES}
        for entity, rows in data.items():
            for row in rows.values():
                self.assertIs(row["synthetic"], True)
                for field, target in {
                    "student_id": "students",
                    "tutor_id": "tutors",
                    "course_id": "courses",
                    "lesson_id": "lessons",
                    "payment_id": "payments",
                    "booking_id": "bookings",
                }.items():
                    if field in row:
                        self.assertIn(row[field], data[target])
                if entity in ("students", "tutors"):
                    self.assertTrue(row["email"].endswith("@amaris.test"))
                    self.assertIsNone(row["mobile"])
                    self.assertNotIn("password", row)
                if entity == "payments":
                    self.assertEqual(row["provider"], "mock")
                    self.assertIsNone(row["gateway_verified_at"])
                if entity == "invoices":
                    payment = data["payments"][row["payment_id"]]
                    self.assertEqual(row["total_minor"], payment["amount_minor"])
                    self.assertEqual(row["total_minor"], row["subtotal_minor"] + row["tax_minor"])
                    self.assertEqual(row["student_id"], payment["student_id"])
                if entity == "progress":
                    self.assertEqual(row["course_id"], data["lessons"][row["lesson_id"]]["course_id"])
                    self.assertTrue(0 <= row["percent"] <= 100)

    def test_invalid_arguments_fail(self):
        for options in (
            {"students": 0},
            {"seed": -1},
            {"tutors": True},
            {"courses": 1.5},
        ):
            with self.assertRaises(ValueError):
                Factory(**options)
        for args in (
            ("unknown",),
            ("students", -1),
            ("students", 2, 1),
            ("students", 0, 101),
        ):
            with self.assertRaises(ValueError):
                list(Factory().rows(*args))

    def test_committed_smoke_fixture_matches_factory(self):
        directory = Path(__file__).parent / "fixtures" / "smoke"
        manifest = json.loads((directory / "manifest.json").read_text())
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "generated"
            generate(Factory(**manifest["factory"]), output)
            for path in output.iterdir():
                self.assertEqual(path.read_bytes(), (directory / path.name).read_bytes())

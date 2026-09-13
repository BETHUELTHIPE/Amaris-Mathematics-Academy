"""Deterministic factories with stable IDs, timestamps and linked records.

Only algorithmically generated data is accepted. No database, network, Faker
version, wall clock, environment variable or production export is consulted.
"""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import NAMESPACE_URL, uuid5

SCHEMA_VERSION = 1
EMAIL_DOMAIN = "amaris.test"
EPOCH = datetime(2026, 1, 1, tzinfo=UTC)
ENTITIES = (
    "students",
    "tutors",
    "courses",
    "lessons",
    "payments",
    "bookings",
    "progress",
    "invoices",
)


@dataclass(frozen=True)
class Factory:
    seed: int = 1475
    students: int = 100
    tutors: int = 10
    courses: int = 20
    lessons_per_course: int = 6

    def __post_init__(self):
        for name, value in asdict(self).items():
            minimum = 0 if name == "seed" else 1
            if type(value) is not int or not minimum <= value <= 10_000_000:
                raise ValueError(f"{name} must be an integer between {minimum} and 10000000")

    @property
    def counts(self):
        return {
            "students": self.students,
            "tutors": self.tutors,
            "courses": self.courses,
            "lessons": self.courses * self.lessons_per_course,
            "payments": self.students,
            "bookings": self.students,
            "progress": self.students,
            "invoices": self.students,
        }

    def id(self, entity, index):
        return str(
            uuid5(
                NAMESPACE_URL,
                f"https://amaris.test/fixtures/v{SCHEMA_VERSION}/{self.seed}/{entity}/{index}",
            )
        )

    def value(self, field, index, limit):
        digest = sha256(f"{SCHEMA_VERSION}:{self.seed}:{field}:{index}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % limit

    def row(self, entity, index):
        if entity not in ENTITIES or type(index) is not int or not 0 <= index < self.counts[entity]:
            raise ValueError("Entity or index outside the fixture configuration")
        row = {
            "id": self.id(entity, index),
            "synthetic": True,
            "fixture_version": SCHEMA_VERSION,
            "seed": self.seed,
            "created_at": EPOCH.isoformat(),
        }
        if entity in ("students", "tutors"):
            role = "student" if entity == "students" else "tutor"
            row.update(
                first_name="Synthetic",
                last_name=f"{role.title()} {index:07d}",
                email=f"{role}-{self.seed}-{index:07d}@{EMAIL_DOMAIN}",
                mobile=None,
                address=None,
                role=role,
                is_active=True,
                email_verified=True,
            )
        elif entity == "courses":
            row.update(
                title=f"Synthetic Mathematics Course {index:05d}",
                slug=f"synthetic-course-{self.seed}-{index:05d}",
                tutor_id=self.id("tutors", index % self.tutors),
                price_minor=45000 + self.value("price", index, 15) * 10000,
                currency="ZAR",
            )
        elif entity == "lessons":
            row.update(
                course_id=self.id("courses", index // self.lessons_per_course),
                title=f"Synthetic Lesson {index:07d}",
                order=index % self.lessons_per_course + 1,
                body="Synthetic practice: solve x + 2 = 5. Subtract 2 from both sides. Therefore x = 3.",
                duration_minutes=40,
                video_url=None,
            )
        else:
            course_index = index % self.courses
            student_id = self.id("students", index)
            course_id = self.id("courses", course_index)
            payment_status = ("paid", "pending", "failed", "refunded")[index % 4]
            amount = 45000 + self.value("price", course_index, 15) * 10000
            row.update(student_id=student_id, course_id=course_id)
            if entity == "payments":
                row.update(
                    reference=f"SYNTHETIC-{self.seed}-{index:07d}",
                    provider="mock",
                    provider_reference=None,
                    gateway_verified_at=None,
                    simulated=True,
                    status=payment_status,
                    amount_minor=amount,
                    currency="ZAR",
                    paid_at=(EPOCH.isoformat() if payment_status in ("paid", "refunded") else None),
                )
            elif entity == "bookings":
                start = EPOCH + timedelta(days=1, hours=index * 2)
                row.update(
                    tutor_id=self.id("tutors", course_index % self.tutors),
                    payment_id=self.id("payments", index),
                    starts_at=start.isoformat(),
                    ends_at=(start + timedelta(hours=2)).isoformat(),
                    status="confirmed" if payment_status == "paid" else "cancelled",
                    meeting_url=None,
                )
            elif entity == "progress":
                percent = self.value("progress", index, 101) if payment_status == "paid" else 0
                row.update(
                    lesson_id=self.id("lessons", course_index * self.lessons_per_course),
                    percent=percent,
                    completed=percent == 100,
                    updated_at=EPOCH.isoformat(),
                )
            else:
                row.update(
                    payment_id=self.id("payments", index),
                    booking_id=self.id("bookings", index),
                    number=f"TEST-INV-{self.seed}-{index:07d}",
                    subtotal_minor=amount,
                    tax_minor=0,
                    total_minor=amount,
                    currency="ZAR",
                    status={
                        "paid": "paid",
                        "pending": "draft",
                        "failed": "void",
                        "refunded": "credited",
                    }[payment_status],
                    delivery="disabled",
                    legal_document=False,
                )
        return row

    def rows(self, entity, start=0, stop=None):
        """Stable slices support deterministic, disjoint worker allocations."""
        if entity not in ENTITIES:
            raise ValueError("Unknown fixture entity")
        end = self.counts[entity] if stop is None else stop
        if type(start) is not int or type(end) is not int or not 0 <= start <= end <= self.counts[entity]:
            raise ValueError("Invalid fixture slice")
        for index in range(start, end):
            yield self.row(entity, index)

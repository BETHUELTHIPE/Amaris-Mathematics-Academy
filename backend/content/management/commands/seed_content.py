from decimal import Decimal
from typing import TypedDict

from django.core.management.base import BaseCommand

from content.models import Course, CourseCategory, CourseModule, NavigationItem, Page, SiteSettings


class CourseSeed(TypedDict):
    title: str
    slug: str
    level: str
    curriculum: str
    price: str
    hours: int
    description: str
    outcomes: list[str]
    modules: list[str]
    featured: bool


COURSES: list[CourseSeed] = [
    {
        "title": "CAPS Grade 12 Mathematics",
        "slug": "caps-grade-12-mathematics",
        "level": "Grade 12",
        "curriculum": "CAPS",
        "price": "950.00",
        "hours": 28,
        "description": "A focused matric programme covering algebra, functions, calculus, geometry and exam technique.",
        "outcomes": [
            "Solve exam-standard problems confidently",
            "Interpret functions and graphs",
            "Build a reliable revision routine",
        ],
        "modules": [
            "Algebra & equations",
            "Functions & graphs",
            "Differential calculus",
            "Analytical geometry",
            "Euclidean geometry",
            "Probability",
        ],
        "featured": True,
    },
    {
        "title": "Mathematical Literacy Grade 12",
        "slug": "mathematical-literacy-grade-12",
        "level": "Grade 12",
        "curriculum": "CAPS",
        "price": "750.00",
        "hours": 22,
        "description": (
            "Practical, visual lessons for finance, measurement, maps, data handling and examination readiness."
        ),
        "outcomes": [
            "Use mathematics in real contexts",
            "Read tables and graphs accurately",
            "Answer multi-step exam questions",
        ],
        "modules": ["Finance", "Measurement", "Maps & scale", "Data handling", "Probability", "Exam practice"],
        "featured": True,
    },
    {
        "title": "Engineering Mathematics N4",
        "slug": "tvet-engineering-mathematics-n4",
        "level": "TVET N4",
        "curriculum": "NATED",
        "price": "850.00",
        "hours": 25,
        "description": (
            "A structured N4 pathway from algebra and trigonometry to complex numbers and introductory calculus."
        ),
        "outcomes": ["Manipulate engineering formulae", "Apply trigonometric methods", "Prepare for NATED assessments"],
        "modules": ["Algebra", "Trigonometry", "Complex numbers", "Functions", "Differentiation", "Integration"],
        "featured": True,
    },
    {
        "title": "University Calculus Foundations",
        "slug": "university-calculus-foundations",
        "level": "University",
        "curriculum": "Higher Education",
        "price": "1200.00",
        "hours": 32,
        "description": (
            "Build the conceptual and procedural foundation needed for first-year limits, derivatives and integrals."
        ),
        "outcomes": ["Reason with limits", "Differentiate common functions", "Model change with integrals"],
        "modules": ["Functions review", "Limits", "Continuity", "Derivatives", "Applications", "Integrals"],
        "featured": False,
    },
    {
        "title": "Linear Algebra Essentials",
        "slug": "linear-algebra-essentials",
        "level": "University",
        "curriculum": "Higher Education",
        "price": "1100.00",
        "hours": 24,
        "description": "A clear visual route through vectors, matrices, systems, transformations and eigenvalues.",
        "outcomes": [
            "Solve linear systems",
            "Understand matrix transformations",
            "Work with eigenvalues and eigenvectors",
        ],
        "modules": ["Vectors", "Matrices", "Linear systems", "Vector spaces", "Transformations", "Eigenvalues"],
        "featured": False,
    },
    {
        "title": "Algebra Recovery Programme",
        "slug": "algebra-recovery-programme",
        "level": "Grades 9–11",
        "curriculum": "CAPS / IEB",
        "price": "450.00",
        "hours": 14,
        "description": (
            "Repair the algebra gaps that block progress in senior mathematics, "
            "with short lessons and deliberate practice."
        ),
        "outcomes": [
            "Simplify expressions accurately",
            "Solve equations step by step",
            "Work confidently with exponents",
        ],
        "modules": ["Number skills", "Expressions", "Equations", "Exponents", "Factorisation", "Word problems"],
        "featured": False,
    },
]


class Command(BaseCommand):
    help = "Create the initial website settings, navigation, pages and mathematics catalogue."

    def handle(self, *args, **options):
        SiteSettings.objects.get_or_create(pk=1)

        navigation = [
            ("Courses", "/courses", 10),
            ("How it works", "/how-it-works", 20),
            ("Pricing", "/pricing", 30),
            ("About", "/about", 40),
            ("Contact", "/contact", 50),
        ]
        for label, url, order in navigation:
            NavigationItem.objects.update_or_create(
                location=NavigationItem.Location.BOTH,
                label=label,
                defaults={"url": url, "order": order, "is_active": True},
            )

        for _order, (title, slug) in enumerate(
            [
                ("Home", "home"),
                ("About us", "about"),
                ("How it works", "how-it-works"),
                ("Pricing", "pricing"),
                ("Contact", "contact"),
                ("Privacy policy", "privacy"),
                ("Student terms", "terms"),
            ],
            start=1,
        ):
            Page.objects.get_or_create(
                slug=slug,
                defaults={"title": title, "is_published": True, "template_key": slug, "summary": ""},
            )

        categories = {}
        for name, slug, order in (
            ("School mathematics", "school", 10),
            ("TVET mathematics", "tvet", 20),
            ("University mathematics", "university", 30),
        ):
            category, _ = CourseCategory.objects.get_or_create(
                slug=slug, defaults={"name": name, "order": order, "is_active": True}
            )
            categories[slug] = category

        for course_order, item in enumerate(COURSES, start=1):
            category_key = (
                "tvet"
                if item["curriculum"] == "NATED"
                else ("university" if item["level"] == "University" else "school")
            )
            course, _ = Course.objects.update_or_create(
                slug=item["slug"],
                defaults={
                    "category": categories[category_key],
                    "title": item["title"],
                    "short_description": item["description"],
                    "description": item["description"],
                    "curriculum": item["curriculum"],
                    "academic_level": item["level"],
                    "price": Decimal(item["price"]),
                    "outcomes": item["outcomes"],
                    "estimated_hours": item["hours"],
                    "featured": item["featured"],
                    "status": Course.Status.PUBLISHED,
                    "is_published": True,
                    "order": course_order,
                },
            )
            for module_order, title in enumerate(item["modules"], start=1):
                CourseModule.objects.update_or_create(
                    course=course,
                    order=module_order,
                    defaults={"title": title, "is_published": True},
                )

        self.stdout.write(self.style.SUCCESS("Amaris CMS starter content is ready."))

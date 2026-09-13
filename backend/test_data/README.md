# Synthetic test data

All test populations are generated from algorithms. Never import real students, tutors, production exports, payment details, phone numbers, addresses or identity documents for large-scale tests. The generator has no database or network access and creates no accounts, bookings, charges, emails or external invoices.

From `backend/`:

```bash
# Small committed smoke fixture: 8 students, 2 tutors, 3 courses, 6 lessons.
python -m unittest discover -s test_data -p 'test_*.py'

# An offline 50,000-student dataset. This does not run a load test.
python -m test_data.generate --seed 1475 --students 50000 --tutors 100 --courses 200 --lessons-per-course 12 --output test_data/generated/capacity-1475

# Validate provenance, counts and content against the generator itself.
python -c 'from load_tests.synthetic import verify_dataset; verify_dataset("test_data/generated/capacity-1475/manifest.json")'
```

The same schema version, seed and count parameters produce byte-identical files across runs. UUIDv5 IDs, timestamps, prices and relationships are stable. Changing a seed creates a separate ID space. Each entity has its own NDJSON file; the manifest records factory configuration, counts and SHA-256 hashes. Generation streams records without retaining the population in memory. Existing outputs are never replaced. Large generated datasets stay out of Git and production images; regenerate them when needed.

| Fixture | Properties |
| --- | --- |
| Students | Labelled synthetic names; reserved `amaris.test` emails; no phones, addresses or passwords |
| Tutors | Separate deterministic IDs and reserved emails; no production access |
| Courses | Tutor relationship, stable slug, ZAR price in integer cents |
| Lessons | Existing course relationship, stable order, synthetic text, no external video |
| Payments | Mock only; paid/pending/failed/refunded scenarios; no gateway verification or real provider reference |
| Bookings | Student/course/tutor/payment relationships; deterministic two-hour slots; no meeting creation |
| Progress | Student/course/lesson relationships; 0–100% with a consistent completed flag |
| Invoices | Mock payment/booking relationship; integer totals; explicitly not legal documents; delivery disabled |

Use factories directly in Python tests:

```python
from test_data.factories import Factory

fixtures = Factory(seed=1475, students=50000, tutors=100, courses=200)
student = fixtures.row("students", 123)
payment = fixtures.row("payments", 123)
# Deterministic disjoint slices for parallel workers:
worker_rows = fixtures.rows("students", start=1000, stop=2000)
```

These are neutral test records, **not Django `loaddata` fixtures**. Existing Django models cover students, courses, lessons, payments and aggregate enrollment progress. Tutor, booking and invoice models are not present on this branch. Payment's production provider choices deliberately exclude `mock`. Any future staging import adapter must map records to the actual schema, use an isolated disposable test database, disable messaging/periodic reconciliation, and preserve the mock-payment boundary. Do not insert simulated `paid` records into the production Payment table or alter production provider validation to accommodate tests. No schema migrations or production data writes are included here.

The staging runner verifies both deterministic file contents and server-reported test isolation before authenticated/write load tests. See [load-test setup](../load_tests/README.md). Passwords and session tokens are short-lived staging secrets and must never be exported in fixtures. Use a dedicated provider test project; fixture `email_verified` flags are scenario data and do not bypass live authentication.

Production smoke testing uses the separately provisioned `synthetic-smoke@amaris.test` account, verified and pre-entitled before a release. Its password stays in the protected production environment. The smoke runner does not generate/import data, register accounts, create payments, book lessons, update progress or deliver invoices.

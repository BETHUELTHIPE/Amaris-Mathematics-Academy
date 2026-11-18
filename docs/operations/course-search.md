# Course search improvement

## User-visible changes

- Search every published course on the server instead of filtering only the first downloaded page.
- Match all search words in any order across title, short description, curriculum, level and category name.
- Support common aliases such as `maths`, `maths lit`, `matric`, `gr.12` and `NC(V)`.
- Rank exact and prefix title matches first; support explicit price, title and newest sorting.
- Include CAPS, IEB, TVET and University filters and an exact grade/academic-level field.
- Preserve search, programme, level and sort in pagination and shareable URLs.
- Add a Search shortcut to the shared header.
- Show real result counts, suggested topics and Clear all. Explain invalid input separately from a backend outage.
- Never replace genuine empty results or a configured CMS failure with sample products.
- Load homepage featured courses through the dedicated featured endpoint rather than filtering page one.

## Public API

`GET /api/v1/courses/?search=maths+matric&programme=IEB&academic_level=Grade+12&ordering=price&page=1&page_size=24`

The existing course-list response shape is unchanged: `count`, `next`, `previous`, `results`.

Search is capped at 100 normalized characters and eight unique search terms. Responses default to 24 courses and have a 48-course maximum. Featured responses are capped at six courses. Relevance and explicit ordering end with a primary-key tie-breaker to prevent duplicate/missing records between equal-ranked pages.

Only currently published courses in active categories appear. Drafts, archived courses, scheduled future publication, private lesson text, file locations and student/tutor personal data are not searched or exposed. Unpublished modules are excluded from lesson counts.

Lesson totals use a correlated subquery instead of a catalogue-wide lesson JOIN/GROUP BY. This limits response work, but does not prove a PostgreSQL latency target or 50,000-course capacity. Metadata `icontains` searches can still scan rows; capture PostgreSQL query plans and staging p95 latency before claiming scale. No database migration, extension or index has been applied by this change.

## Verification observed

- New Django search regressions: 16 passed.
- Broader backend suite: 264 tests completed successfully, five environment-dependent skips. This used SQLite, local cache aliases and plain test static-file storage; it is not PostgreSQL/Redis staging acceptance.
- Frontend helper and real CMS-client runtime tests: 12 passed. Fetches were mocked; no external backend was contacted by those tests.
- Scoped TypeScript check for the search component and its CMS/helpers: passed. This is not a full frontend production build.
- Ruff and Black for affected Python files: passed; migration drift check: no changes detected.
- Actual shared-browser check of the server-rendered component: desktop form submission, URL and price order verified using labelled sample data. A narrow 390px frame (375px usable viewport) showed stacked controls and no horizontal content overflow.

Focused commands:

```sh
cd backend
python manage.py test content.test_course_search --noinput
python manage.py makemigrations --check --dry-run
ruff check content/course_search.py content/views.py content/test_course_search.py content/test_integrations.py
black --check content/course_search.py content/views.py content/test_course_search.py content/test_integrations.py
```

```sh
cd frontend
node --test tests/course-catalog-search.test.mjs tests/course-catalog-cms.test.mjs
```

The API payload integration assertion is updated on each branch to stop coupling the CMS client to the obsolete literal `page_size=100` URL. The response payload assertions remain intact.

## Rollout and rollback

Use paired draft changes based on the current backend `production-release-20260923` and frontend `render-live-current-20260918` branches. Deploy the backwards-compatible backend first, then the frontend after CI and staging acceptance. The server remains the authority for prices and payment access.

PR #430 contains overlapping catalogue-pagination/subquery work based on an older branch. Reconcile that overlap during review; do not blindly merge both implementations or overwrite later navigation, authentication or storage changes.

Before production: run the complete frontend lint/type/build/accessibility gates, PostgreSQL/Redis regression tests, and real staging search/booking smoke tests. Verify CMS_API_URL and approved release SHAs. Production deployment is not performed by this work.

Rollback requires only the prior application revisions; no schema or persisted search-history data changes are introduced.

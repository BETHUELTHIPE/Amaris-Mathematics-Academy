# Tutor recruitment

## Applicant journey

The matching frontend adds `/tutor/apply` (Become a tutor in navigation), `/tutor/register`, `/tutor/verify-email` and `/tutor/apply/login`. Existing Amaris accounts can sign in without registering again. Applicants verify their Supabase email, complete a form and attach 1–5 PDF/JPEG/PNG qualifications (5 MiB per file, 15 MiB total). A successful receipt shows a reference, review status, private downloads and the acknowledgement email state.

The account is not an approved tutor. No user-submitted role or application status grants the existing tutor dashboard or the Django Tutors group. Recruitment staff review qualifications manually. The existing tutor approval process remains a separate administrator action.

## Backend contract

- `GET /api/v1/tutor-applications/`: own application or null.
- `POST /api/v1/tutor-applications/`: verified bearer session and multipart fields/documents; server binds identity/email. One immutable submission per Supabase user. Repeated submission returns the existing receipt.
- `GET /api/v1/tutor-applications/documents/<uuid>/`: owner-only attachment download, no public storage URL, no-store/nosniff/sandbox headers.
- `POST /api/v1/tutor-applications/acknowledgement/`: retry own pending acknowledgement, respecting delivery backoff; a sent acknowledgement is a no-op.

Fields: full_name, phone, location, qualification, institution, subjects, programmes (repeated values: caps/ieb/tvet/university), levels, experience_years, teaching_experience, availability, motivation, consent and repeated documents. Qualification and MIME signatures are validated before storage. Storage/database failure rolls back metadata and attempts cleanup of written objects.

## Private storage and review

`tutor_qualifications` uses the existing private CMS/admin Supabase S3 configuration, not the student-owned file bucket. Keys use UUIDs without applicant names. The local-development fallback is outside public MEDIA_ROOT. Both recruitment tables enable RLS and revoke PUBLIC/anon/authenticated privileges in additive migration `0012_tutor_recruitment`; only Django serves their records.

Production storage inspection on 2026-10-15 found both configured buckets private. Existing storage.objects policies cover owner-prefixed student-bucket files only; there are no public/authenticated CMS-bucket policies. Do not add public read policies for recruitment files.

Django Admin → Tutor applications lets staff with application view/change permission inspect qualifications and record review status/notes. Ordinary staff without recruitment permission are denied downloads. Notes and reviewer identities are never returned to applicants. There is no automated suitability decision or grant of teaching access. Documents can be reviewed only through the permission-checked admin download. Routine admin deletion is disabled: authorised privacy operations must explicitly remove objects from the private bucket and delete the matching records after assessing the request and retention requirements.

## Acknowledgement delivery

The application and documents commit before SMTP is attempted. The existing Django mail backend sends a plain-text/HTML acknowledgement to the authoritative verified account email, with the application reference and no qualification attachments. SMTP failure preserves the application with pending delivery, attempt count, next retry time and a non-sensitive error class. The applicant sees pending delivery and can retry after backoff.

`content.tasks.deliver_tutor_application_acknowledgements` runs on notifications; beat retries every 30 seconds. Existing Render service discovery on 2026-10-15 returned no workers/cron services. Immediate submission/retry delivery works with the web service's configured SMTP; unattended outage recovery additionally requires a running notifications worker and beat, or an existing scheduler running:

```sh
cd backend
python manage.py deliver_tutor_acknowledgements --limit 100
```

Do not mark external delivery verified until a controlled inbox receives the real message. Row locks prevent concurrent successful sends, but SMTP does not provide an exactly-once guarantee after a process crash between acceptance and database commit.

## Release

Backend PR targets production-release-20260923. Matching frontend PR targets render-live-current-20260918. Deploy backend/migration first and verify private storage/mail configuration, then frontend. An unauthenticated applicant may browse the page, but submission and downloads require verified authentication. Neither release is automatically authorised by preparation. Do not overwrite either production branch or mix their divergent histories.

Before live release: required exact-head CI, current production backup/readiness, migration review, isolated staging upload/download/permission checks, controlled Supabase signup/login and SMTP inbox acceptance. No production database, file, Auth user or message was created during local implementation tests.

## Local verification

The full Django suite, formatting/lint/type checks, migration drift and strict OpenAPI validation are run for this change. Frontend unit tests exercise registration/verification/login redirects, duplicate-signup privacy, same-origin protection, authenticated multipart forwarding, size limits and JavaScript-free submission. The paired browser harness in `frontend/e2e/tutor_recruitment.py` runs real frontend/Django processes against isolated SQLite/private files, a fake Auth server and captured mail. It must not be represented as live Supabase or SMTP acceptance.

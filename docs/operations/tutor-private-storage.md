# Three private storage buckets

| Owner | Bucket |
| --- | --- |
| Students | `Amaris Mathematics Academy` |
| Tutors | `amaris-tutor-files` |
| Django Admin | `amaris-cms-files` |

Structured records remain in protected Supabase PostgreSQL, linked to file keys.
Tutor applications and all six document categories, leave/resignation PDFs and
tutor-uploaded video source/thumbnail/captions belong in the tutor bucket.
Admin branding, course assets, Admin-uploaded media and performance PDFs belong
in the Admin bucket. Ownership, rather than the dashboard used, determines the
bucket: a tutor using Django Admin still uploads into the tutor bucket.

Configure the existing service/worker with server-only S3 credentials and:

```
SUPABASE_S3_ADMIN_BUCKET=amaris-cms-files
SUPABASE_S3_TUTOR_BUCKET=amaris-tutor-files
SUPABASE_S3_STUDENT_BUCKET=Amaris Mathematics Academy
SUPABASE_S3_REQUIRED=true
```

All three names are enforced and production never falls back to local disk.
Create the tutor bucket PRIVATE with the same 50 MiB limit as the existing
buckets, using the Supabase dashboard or Storage API. No browser policies are
needed: Django authorizes tutor/owner/Admin requests. Do not modify Storage
metadata using SQL. Never expose S3 credentials in frontend configuration.

Migration 0028 changes only Django state, with no database operations or file
moves. Existing Admin media keys and the legacy CMS prefix remain readable.
New tutor media gets server-generated `videos/tutor-uploads/` keys; student
storage is unchanged. Admin report PDFs explicitly use `admin_private`.
Development private forms/reports have no public media URL.

Rollout requires provisioning the third bucket before deploying. At the latest
read-only inspection only the student and Admin buckets existed. Dashboard
sign-in was interrupted; tutor bucket creation is NOT VERIFIED. No files were
moved/deleted and no production emails/test uploads were created. Render was
billing-suspended at the previous inspection; live acceptance remains pending.

Before rollout, inventory any historical tutor files in the Admin bucket using
application references. Copy through Storage API, verify bytes/hash and private
downloads, then migrate references safely; retain originals until verified.
The earlier audit found no objects under known tutor prefixes, but does not
rule out files with other naming conventions. Do not silently fall back to
Admin storage when a tutor file is missing from its designated bucket.

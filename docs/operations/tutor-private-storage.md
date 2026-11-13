# Tutor and Admin storage

In Supabase project `epkcuseloinygkakxxdu`, keep `amaris-cms-files` private.
All tutor application attachments (ID, CV, matric certificate, academic records,
tertiary certificate and other document), tutor videos, thumbnails, captions,
resources, leave/resignation PDFs and Admin performance report PDFs use this
bucket. All other Django Admin file/image fields use the same CMS storage.
Student documents and invoices use the separate private
`Amaris Mathematics Academy` bucket.

Submitted structured fields, tutor profiles, reviewer decisions, form payloads,
file metadata and delivery audit records remain in Supabase PostgreSQL. Storage
holds file content; it does not replace the protected relational database.
Leave/resignation PDFs include the submitted form details on the academy
letterhead. Owner/Admin download permissions and email behavior are unchanged.

## Configuration and deployment

Configure the existing Django service and any notification worker with the same
server-only S3 endpoint, region, access key and secret, plus:

```
SUPABASE_S3_ADMIN_BUCKET=amaris-cms-files
SUPABASE_S3_STUDENT_BUCKET=Amaris Mathematics Academy
SUPABASE_S3_REQUIRED=true
```

Never put S3 credentials in browser/`NEXT_PUBLIC_*` configuration. A swapped,
shared or misspelled bucket name, incomplete S3 configuration or HTTP endpoint
prevents startup. With every S3 variable absent and `REQUIRED=false`, production
can start but file storage operations raise an error; nothing is written to
ephemeral/local storage. Applicant/personnel/video APIs return unavailable and
do not record a successful submission when saving the required file fails.

Apply migration `0027_private_tutor_document_storage` after its parent migrations.
It changes Django's storage selection only, without moving objects or changing
their keys. The existing `SUPABASE_STORAGE_ENABLED` CMS prefix is preserved;
do not toggle it for this rollout. Both PDF fields explicitly select private
CMS storage. Public media paths cannot expose locally generated tutor PDFs:
development uses `private-tutor-files` outside `MEDIA_ROOT` and has no public URL.
Existing development-only PDFs in `media/tutor-personnel` or
`media/admin-performance` need copying to the same relative key under
`private-tutor-files` before testing downloads; this does not affect cloud files.

## Verification

The routing tests stub S3 requests and verify actual upload requests target the
CMS bucket, along with student bucket separation, private signed URLs, bucket
misconfiguration rejection, no production disk fallback and local PDF privacy.
Existing workflow tests cover ownership, save failures and email idempotency.
These tests do not send real emails or upload synthetic files to production.

On 13 November 2026, read-only Supabase inspection confirmed both buckets private
and found no objects under the new tutor application/personnel/video/performance
prefixes (including their legacy `cms/` variants) in either bucket. This is not
proof about files using other historical naming conventions. No files were moved
or deleted. Production/staging Render services are billing-suspended; end-to-end
live upload and download verification remains pending service restoration and
deployment of the dependent feature releases. Do not treat a passing unit test
as live storage acceptance.

After deployment, use an authorized tutor submission to confirm the returned
record and private object in the CMS bucket, owner/Admin download success,
cross-user rejection and absence from the student bucket. Never edit
`storage.objects` rows directly to move a file. Historical misplaced files need
an inventory, a verified Storage API copy and a retained original until the
corresponding application references and authorized downloads are verified.

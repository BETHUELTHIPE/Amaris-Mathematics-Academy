# Request a Topic Video: private 1 GiB upload rollout

Status: **feature branch only — NOT enabled on production**.

Students may choose individual files or a browser-supported folder; up to **200 files / 1 GiB
combined**. Accepted: PDF, JPEG, PNG, GIF, WebP, DOCX, XLSX, PPTX, TXT, CSV, ZIP,
MP4 and WebM. Folder-relative paths are preserved in the private document metadata.

## Flow

1. Verified student creates a server-priced video request in pending-payment state.
2. The frontend requests S3 multipart upload initialization through an authenticated
   Next route backed by Django's Supabase-token authorization.
3. Each 8 MiB file part uploads **directly** to the private Supabase student S3 bucket
   using a short-lived signed URL (no S3 credentials are sent to the browser).
4. Django locks the student's unpaid request, completes the multipart upload,
   verifies S3 HEAD content-type and exact file length, enforces the combined quota
   and records the private key in VideoRequestDocument.
5. Only when every file is attached does the UI expose PayFast payment.
   Tutor fulfillment still requires provider-verified payment.

There is deliberately no generic ZIP extraction, automatic file rendering, public
download URL or file-bytes-over-Django proxy. Large directly-uploaded files have an
empty `sha256` database field: S3 validates multipart ETags, but **no end-to-end SHA-256
claim** is made for these files.

## Staging acceptance / prerequisites

- Existing private bucket: `Amaris Mathematics Academy`, not the CMS bucket.
- On **2026-10-10**, the real project's private student bucket was configured with
  `file_size_limit=52428800` (50 MiB), so a 1 GiB upload **will not work yet**.
- Confirm the Supabase project plan supports >=1 GiB **global** file size and raise
  the private student bucket limit to >=1 GiB. Never silently upgrade a paid plan.
- Configure the S3 endpoint and server-only S3 credentials already supported by
  the Django student-private storage backend.
- Configure browser-origin cross-origin S3 multipart PUT requests and expose the
  `ETag` response header (test actual Safari/Android/desktop browsers).
- Set `VIDEO_REQUEST_LARGE_UPLOAD_ENABLED=true` **on staging only** after checking the
  previous items. The default is false and fails closed.
- Exercise real authenticated staging upload: a 1 GiB synthetic file, a folder with
  several images/Office documents, a failed/interrupted part, and repeated / duplicate
  completion. Check ownership, 1 GiB quota, 200-file quota, expiry cleanup, cost/bandwidth,
  object metadata, and private bucket accessibility.
- Add malware scanning/quarantine before staff downloads untrusted Office/ZIP/media
  files; this is a release blocker for unrestricted live public uploads.
- Run CI + security checks and staging acceptance before promoting to production.

For S3 multipart API support, see
https://supabase.com/docs/guides/storage/s3/compatibility and
https://supabase.com/docs/guides/storage/uploads/s3-uploads.
For limits, see https://supabase.com/docs/guides/storage/uploads/file-limits.

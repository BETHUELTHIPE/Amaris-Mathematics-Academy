# Private topic-video documents: 1 GB limit

The proposed topic-video upload limit is 1,073,741,824 bytes per file and across
the complete selection. At most five PDF, JPEG or PNG documents are accepted.

The browser checks file metadata before submitting. The frontend forwards the
multipart stream with backpressure and a 1 MiB allowance for fields/boundaries.
Django validates actual file length, content signature and SHA-256 in bounded
reads, then saves the uploaded file stream into `student_private` storage.
The existing verified-account, owner checks and private response headers remain
in effect. Recruitment qualifications retain their separate 5 MB / 15 MB policy.

The Docker Nginx configuration raises the body limit only for the topic-video
checkout endpoint and denies the local private-student media prefix. Render's
managed web services do not use this Nginx configuration.

## Activation prerequisites

On 24 October 2026 a read-only production check showed that both existing
Supabase buckets are private and have `file_size_limit=52428800` (50 MiB).
No bucket, subscription or production runtime setting was changed.

Before releasing the frontend's 1 GB message:

1. Confirm the Supabase global file limit and private student bucket support at
   least 1,073,741,824 bytes. A bucket limit cannot exceed the project global
   limit. Do not purchase or upgrade a plan without the user's authorization.
2. Verify available temporary disk, memory and request-duration limits on the
   existing Render services. The Cloudflare build is not evidence that a
   Cloudflare account accepts 1 GB HTTP requests.
3. Run an authenticated staging upload through the actual Render frontend,
   Django and private Supabase storage. Check a 1 GB file, combined quota,
   interruption, invalid types, anonymous denial and another student's denial.
4. Promote the matching backend and frontend PRs after their required CI checks.

No schema migration is required. Roll back the application versions together.
The local sparse-file boundary and stream tests do not establish successful
1 GB storage delivery in staging or production.

Reference: https://supabase.com/docs/guides/storage/uploads/file-limits

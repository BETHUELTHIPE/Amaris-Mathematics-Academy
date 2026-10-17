# Request a Video — private resumable supporting documents

The **Amaris Mathematics Academy** student bucket in Supabase is `Amaris Mathematics Academy` (not `amaris-cms-files`). The bucket must remain **private**.

## Current storage prerequisite

On 2026-10-09 the existing production student bucket was verified private with `file_size_limit = 52428800` (50 MiB). **This must be raised to at least 1073741824 bytes (1 GiB), and the Supabase project's GLOBAL upload limit must also allow 1 GiB, before the new UI can upload files of this size.** Free projects cannot exceed the documented 50 MB global limit; a billing-plan change requires separate approval. Do not claim that 1 GB works live without an actual successful end-to-end upload.

## Implemented flow

1. Verified student creates a pending video request with the existing server-priced PayFast workflow. The checkout POST excludes file bytes.
2. The private student status endpoint returns a request-specific `student_uuid/video-requests/request_uuid/documents/` prefix and the remaining file quota only for pending payment.
3. The same-origin upload-session handler checks identity, expiry, ownership, allowed MIME type, 1 GiB per-file and aggregate quota. With the student's Supabase session, it requests a time-limited upload token using `createSignedUploadUrl` for a randomly generated object key.
4. Browser uploads directly to the Supabase TUS endpoint at `<project>.storage.supabase.co` using 6 MiB chunks, progress feedback and HEAD-based retry/recovery. No large payload flows through the application runtime. The token and upload URL are kept in memory; the service-role key never reaches the browser.
5. An authenticated Django endpoint checks request ownership, pending-payment status, path prefix, file count and aggregate size, then reads storage metadata and at most 8 bytes to check PDF/JPEG/PNG signatures before storing the document metadata.
6. Only after all selected uploads have been registered does the student see the existing PayFast checkout form. Payment and queueing still require server-side verification.

Up to **five** PDF/JPEG/PNG files are supported, with a **1 GiB aggregate limit**. The legacy 10 MiB document path remains intact for existing API clients.

## Safeguards and operational follow-up

- Student-specific Supabase RLS INSERT/SELECT policies on `storage.objects` must remain enabled; never make the bucket public.
- Keep the backend `SUPABASE_S3_STUDENT_BUCKET` configured to the same bucket name, with S3 credentials restricted to the server.
- Backend stores no fabricated checksum for a streamed file. `sha256` is blank until separately verified; do not treat it as evidence of full-file integrity.
- Protect against malware and document content risks before tutors preview files. The first-byte MIME/signature check is **not antivirus scanning**.
- Add periodic garbage collection for orphaned signed uploads that were not successfully registered. The existing unpaid-request cleanup removes registered documents but does not by itself remove abandoned, unregistered TUS objects.
- Storage requests from the browser must be allowed by the site's CSP and Supabase Storage CORS policies. The existing wildcard `connect-src https://*.supabase.co` includes the direct storage hostname.
- Do not begin real PayFast transactions during tests.

## Release verification

Before enabling 1 GiB uploads in production: validate the account-level and bucket file limits, apply them with approved operational controls, run mocked/CI unit tests, then upload a synthetic >50 MiB file and a synthetic 1 GiB file to staging. Confirm that a second student cannot register another student's path; files are private, size and signature rejections work, payment is not charged until all uploads finish, and the request record refers to the correct private object. Measure 1 GiB upload progress, interruptions and resume on a realistic network. Require the project's existing staging, security, backup/restore and production-approval gates before deployment.

# Tutor video submissions and Admin activity alerts

Approved tutors can submit lesson videos from the tutor dashboard after this backend and its paired frontend are released. The existing Django Admin video form also records a tutor's new media upload or private YouTube registration. Metadata-only edits do not create another upload alert.

## Submission and review

- Supabase must confirm the tutor's email and the matching active Django user must belong to the **Tutors** group. Browser-supplied roles, tutor IDs, publication flags and storage paths are never trusted.
- A submission requires title, curriculum (CAPS/IEB/TVET NATED/TVET NC(V)/University), subject, grade/level/module, topic and one supported video file. Duration is optional and clearly labelled tutor-reported.
- MP4/M4V, WebM and modern MOV containers are accepted. MIME/extension and container header checks are applied; this is not a media-transcoding or malware-scanning pipeline. The maximum is 50 MiB, configurable downward, matching the production bucket limit observed on 13 November 2026. Both named production buckets were read-only verified private; their configuration was not changed. The multipart handler enforces the limit while receiving bytes, including chunked or multiple-part requests.
- Videos are stored through the existing private CMS Supabase storage in **amaris-cms-files**. Portal uploads are draft, with no preview or scheduled publication, and never attach themselves to a published course. Admin reviews and links approved content using the existing publishing workflow. This feature does not add transcoding or a new student playback service.
- Tutors can replace only their own unpublished assets. Published assets require a new draft; other tutors' assets cannot be replaced. Tutor-staff Admin access is scoped to owned videos and cannot publish them through bulk actions or change forms. Existing authorised academy publishing remains available.
- Storage writes are streamed, not base64-encoded. The portal forwards the authenticated multipart body without buffering it into a JSON or FormData object on the server. Hosting/proxy upload limits must be checked in staging before advertising a live size limit.

## Detailed Admin email

Every committed tutor upload creates a private `TutorVideoUpload` audit/outbox row. The alert contains the actual tutor identity/email, video title, curriculum, subject, level, topic, filename, actual byte size, declared duration, provider, upload activity, SAST timestamp, publication status and video/activity references. A trusted HTTPS `PUBLIC_API_URL` supplies the authenticated Django Admin review link. No signed playback URL, object key, credentials, student records or video attachment is emailed.

The recipient is `TUTOR_VIDEO_ADMIN_EMAIL`, or the academy email from Django Site Settings when empty. It is validated and cannot be supplied by the tutor. Delivery is held for review if the configured Admin address changes before sending.

The shared official letterhead includes the approved academy logo, navy/gold styling, Managing Director, address, phone, email, reference and footer. Its inline logo works without an external image request. Payment confirmations, live-class confirmations/reminders, video-request emails, recruitment acknowledgements, tutor payment confirmations and enquiry replies now use the same helper. Original plain text, recipients, headers and invoice PDFs are preserved; logo parts are inline and applicant documents remain private. Supabase Auth templates and independently deployed frontend mailers are separate systems; this code does not modify their hosted configuration.

## Reliability

The existing singleton Celery Beat publishes `content.tutor_video_tasks.deliver_tutor_video_admin_alerts` every 30 seconds to the `notifications` queue, including notifications-only Beat. Each sweep processes at most 50 queued activities. No SMTP call or broker dispatch blocks the upload request. Committed outbox rows recover when the worker returns; uncommitted/failed database transactions cannot produce an email.

Tutor-scoped upload idempotency keys prevent a retry from creating another video or alert. Reusing a key with different metadata/file content is rejected. Row locks and a committed `sending` claim prevent overlapping workers from sending the same activity twice automatically.

Known SMTP rejections/zero acceptance retry with backoff, bounded to five attempts. Unknown outcomes, a process crash after acceptance, a changed Admin recipient, or a sending claim older than one hour require review. SMTP acceptance is not proof of inbox receipt. After checking provider logs and confirming **not accepted**, an operator can requeue an ambiguous delivery older than one hour:

```sh
python manage.py review_tutor_video_alert ACTIVITY_UUID --confirm-not-accepted
```

Do not use this to blindly resend mail already accepted by the provider. Read-only delivery/audit records are available in Django Admin. S3 writes and SQL commits cannot be one distributed transaction: failed portal registrations attempt private-object cleanup; failed Admin transactions can leave private orphan objects for operator cleanup, but do not send alerts.

## Deployment acceptance

1. Reconcile migration leaves with other open features, then apply additive migration `0024_tutor_video_upload_alerts` (depends on production `0018`). It adds optional video context/uploader fields and the private outbox; the new table enables RLS and revokes public/anon/authenticated table grants. No browser Data API access is granted.
2. Confirm `student_private` still points to the student bucket and the default CMS storage points to the isolated private **amaris-cms-files** bucket. Production portal enablement requires private Supabase S3 configuration.
3. Configure `PUBLIC_API_URL` as the backend's HTTPS origin and the intended Admin email. Existing SMTP, notification worker and singleton Beat must be ready; no paid services are created by this change.
4. Release the paired frontend. `TUTOR_VIDEO_UPLOADS_ENABLED` defaults false; the dashboard displays its form only when the backend enables the capability. Enable only in isolated staging first. `TUTOR_VIDEO_MAX_UPLOAD_BYTES` can reduce the 50 MiB cap.
5. Verify a genuine approved tutor upload, private storage, ownership, draft review, correct SAST email details, inline letterhead and actual Admin inbox receipt. Repeat the same upload key, simulate a rejected/uncertain SMTP outcome, and verify the original invoice/student/tutor emails still arrive with unchanged PDFs.
6. Activate the reviewed production release after those checks. Local/test-mail-backend and CI results are not live storage or genuine inbox evidence.

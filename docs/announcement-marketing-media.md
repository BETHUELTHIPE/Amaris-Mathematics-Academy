# Amaris Marketing Announcements: images, videos and PDF attachments

- Superuser-managed Django Admin: `/admin/content/announcement/` (create/edit/publish announcements; add media inline), and `/admin/content/announcementmedia/` (manage attachments).
- Supported types: JPEG, PNG, WebP, MP4, WebM and PDF. Single-file size limit: 100 MiB. The Django model validates extensions, binary file headers and size; this is **not** a substitute for antivirus scanning or a video transcoding pipeline.
- Upload path: `marketing/announcements/YYYY/MM/` under the **CMS storage bucket**, the existing Django `default` S3 storage. Configure Render environment variables `CMS_STORAGE_BUCKET_NAME=amaris-cms-files`, `STUDENT_STORAGE_BUCKET_NAME`, `AWS_S3_ENDPOINT_URL`, access key, secret and region as appropriate for the existing Supabase S3 integration. Do not put access keys in the code or public frontend.
- Production upload storage MUST be checked before rollout; the existing Django settings permit a filesystem fallback for local development. Public delivery **fails closed** without the CMS bucket setting.
- Public page: `/announcements`. Reads only published, active, unexpired announcements via existing read-only API; each media resource is accessed via `/api/v1/marketing-media/<id>/`, which checks publication state before returning a short-lived S3 URL redirect.
- Visitors may view/download already published assets; only an authenticated Django **superuser** may create, view in the admin, update or delete announcements and attachments. Ordinary staff and tutors cannot administer content.
- Accessing public marketing images/videos requires publication; don't upload student data, tutor data, invoices or private course videos here.
- Django Admin delete removes the database row, not necessarily the original S3 object; create an audited garbage-collection workflow before promising physical S3 file deletion.
- Cache: announcement listings may take up to 60 seconds to refresh after publication. Media redirects are no-store.
- Deployment: apply `content.0008_announcement_media` on staging, test actual Supabase S3 upload and signed download, then deploy frontend. Production promotion requires a genuine backup and explicit approval. No real payments are involved.

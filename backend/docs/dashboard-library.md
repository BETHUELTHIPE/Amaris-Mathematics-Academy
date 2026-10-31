# Dashboard Library

The Library shares teaching resources with every verified student. It is independent of paid course resources and never changes enrolment or payment access.

- Students: **Dashboard → Library** (`/dashboard/library`), search by title/subject/grade/module, filter by document type and download published resources.
- Approved tutors: **Tutor dashboard → Library** (`/tutor/dashboard/library`), upload documents, download published resources and publish/hide their own uploads. Approval uses the existing active Django user in the `Tutors` group and verified Supabase email. Recruitment applications and browser role claims do not grant access.
- Django administrators: **Academy content → Library**, upload, replace, edit, publish, hide or delete resources using normal model permissions. Admin downloads include drafts and require the model view/change permission.

Each resource has a title, description, type (textbook/worksheet/study notes/other), subject, grade/level/module, uploader and publication status. Uploads require permission to share. Allowed formats: PDF, DOCX, XLSX, PPTX, UTF-8 TXT. Maximum 50 MiB, matching the currently inspected private bucket limit; no bucket configuration or plan changes are made.

## Storage and access

`LibraryResource.file` uses the existing default CMS storage, configured for the private `amaris-cms-files` bucket. Storage keys are randomized under `library/` (or `cms/library/` when the existing storage prefix is enabled). Original names are metadata, never storage keys. There is no public resource URL in the list API. Downloads check authorization/publication first and redirect to a short-lived S3 signed URL with attachment headers. Local development uses an authenticated file stream. A signed URL already issued remains usable until its existing five-minute expiry even after hiding a resource.

The additive Django migration `0020_library_resources` creates `content_libraryresource`, enables PostgreSQL RLS and revokes public/anon/authenticated Data API access. Django's server-side database connection is the access boundary. No storage policies or production schemas are changed during implementation. No new dependency, queue or paid service is required.

## API

All API paths are relative to `/api/v1`. All responses are private/no-store.

| Method | Path | Access |
| --- | --- | --- |
| GET | `/student/library/` | Verified active student; published resources |
| GET | `/student/library/{uuid}/download/` | Published resource only |
| GET/POST | `/tutor/library/` | Approved tutor; published plus own drafts / multipart upload |
| PATCH | `/tutor/library/{uuid}/` | Owner only; `is_published` boolean only |
| GET | `/tutor/library/{uuid}/download/` | Published plus own drafts |

Lists accept `q`, `resource_type`, `page`, return `{results, count, page, page_size}` and use a fixed page size of 24. Tutor uploads accept only teaching metadata, file, sharing confirmation and publication status. Identity/size/MIME/original name are server-derived. File content/extension and macro checks apply to API and Django Admin uploads.

## Rollout and acceptance

Deploy the backend migration and code before the paired frontend. Before promotion, verify CMS storage still uses the intended private admin bucket and the frontend points to the matching backend/auth project. Complete a real staging tutor upload, admin upload, student download and hide/permission check. Confirm downloaded bytes and original filename. Repeat at desktop/mobile widths and run accessibility checks. The Render services were observed suspended for billing during implementation, so live acceptance was not attempted.

Rollback application code to the prior release while retaining the additive table and stored documents. Do not reverse the migration or delete learning resources as an application rollback.

## Observed local checks

- `python manage.py test content --noinput`: 222 tests, 5 skipped (existing integration skips); passed on temporary SQLite.
- The above includes 14 Library tests: verified access, upload restrictions, server-owned metadata, exact download bytes, signed URL behavior, hidden resources, ownership, file validation, search/pagination, transient storage failures and Django Admin permissions.
- Django system checks, migration drift check, OpenAPI validation, Black, Ruff and configured mypy checks passed.
- PostgreSQL RLS execution and real Supabase file round trip remain staging acceptance items. Local tests mock external Auth/storage.

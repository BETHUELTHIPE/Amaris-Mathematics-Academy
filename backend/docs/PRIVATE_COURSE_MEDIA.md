# Private course videos: YouTube, AWS S3 and Vimeo

Django Admin: **Academy content → Video assets**. Only active superusers can
view, create, edit, publish, or delete video-asset records. Create course
modules and lessons in the existing Course/Module/Lesson admin screens, then
select a video asset on the lesson. Course metadata, enrollments and lesson
ordering remain in PostgreSQL; the external services store video files.

## Providers and operational boundaries

| Provider | Admin fields | How media gets there | Access |
| --- | --- | --- | --- |
| YouTube | Private YouTube video ID or HTTPS URL | Upload in YouTube Studio, set **Private**, then paste the ID/link | YouTube **Private** requires the viewer's Google account to be explicitly invited by the owner. It cannot serve arbitrary paid students merely by hiding its URL. |
| AWS S3 | **Dedicated private AWS S3 upload** | Upload the media directly using the Admin `aws_file` field | Dedicated **private** S3 bucket, no public ACL, signed object URLs expire after 300 seconds. Django must verify enrollment before ever issuing a signed URL to a student. |
| Vimeo | Private Vimeo video ID or HTTPS URL | Upload in Vimeo, set the appropriate privacy/embed-domain restrictions, then paste the ID/link | Restrict viewing/embed domains in Vimeo and perform server-side enrollment checks before exposing playback data. Storing the ID alone does not confer privacy. |
| Existing CMS videos | Legacy CMS video file | Existing `source_file` records continue unchanged | Storage remains governed by the existing CMS/Supabase S3 configuration. Do not migrate files by editing the storage alias in place. |

**This change adds admin configuration and AWS upload storage; it does not
create automated YouTube or Vimeo uploads.** Those integrations require separate
OAuth/provider credentials, rate-limit handling and an upload/publishing flow.
The public course API deliberately does **not** return video provider IDs,
private storage keys, signed URLs or source files. An authenticated,
enrollment-gated playback API must be implemented and tested before unlocking
paid private videos in the student player. A signed URL is not DRM; it can be
redistributed until expiry.

## Render environment variables

Configure on the **Django backend service**, separately for staging and
production, never in Git or frontend environment variables:

- `PRIVATE_VIDEO_S3_BUCKET_NAME`: existing **private** AWS S3 bucket name.
- `PRIVATE_VIDEO_S3_REGION`: AWS region, e.g. `af-south-1`.
- Prefer a scoped AWS IAM role. If the host cannot use roles, configure
  `PRIVATE_VIDEO_S3_ACCESS_KEY_ID` and
  `PRIVATE_VIDEO_S3_SECRET_ACCESS_KEY` as secret environment variables.
  Both are required together if either is set.

IAM policy must allow only the required `s3:PutObject`, `s3:GetObject`,
`s3:DeleteObject`, and `s3:ListBucket` actions on the private video bucket
and the `private-videos/` prefix. Enable Block Public Access on the bucket,
server-side encryption, versioning and lifecycle policy as appropriate. Do not
create public CDN aliases. Credentials must not appear in Admin forms.

When the bucket is **not configured**, development/tests use isolated local
files. In production, the model blocks creation of `aws_file` references
without the dedicated bucket setting. The existing CMS storage is never
silently changed to this AWS bucket.

## Release checks

1. Review additive migration `content.0005_private_video_providers` and take
   production backup per migration policy.
2. Run `python manage.py makemigrations --check --dry-run`, Django checks and
   `python manage.py test tests.security.test_private_video_assets`.
3. In staging, upload a small test video through Django Admin and verify the
   object exists in the dedicated private AWS bucket (not CMS/Supabase).
4. Verify unsigned anonymous S3 access is denied, a server-generated signed
   URL expires, and non-enrolled students cannot obtain playback access.
5. Validate YouTube private viewer invitations and Vimeo embed restrictions
   using provider accounts without exposing credentials.
6. Promote only after the mandatory staging, security, backup and release
   checks are green. Never claim provider playback works from these model tests.

**Do not set a video as a free preview** merely to bypass payment or enrollment.

"""Tutor-owned private uploads, immutable activity details and idempotent Admin alerts."""

import hashlib
import json
import logging
import uuid
from datetime import timedelta
from pathlib import PurePath
from smtplib import SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from content.models import SiteSettings, VideoAsset
from content.services.branded_email import DEFAULT_EMAIL, apply_letterhead
from content.tutor_video_models import TutorVideoUpload

logger = logging.getLogger(__name__)
MAX_VIDEO_BYTES = 50 * 1024 * 1024


class UploadConflict(Exception):
    pass


def approved_tutor(user):
    return user.is_active and user.groups.filter(name="Tutors").exists()


def inspect_video(upload):
    name = PurePath(upload.name.replace("\\", "/")).name[:180]
    suffix = PurePath(name).suffix.lower()
    types = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}
    if suffix not in types or upload.content_type not in (
        {types[suffix], "video/x-m4v"} if suffix == ".m4v" else {types[suffix]}
    ):
        raise ValidationError("Choose an MP4, M4V, WebM or MOV video with the correct file type.")
    limit = min(MAX_VIDEO_BYTES, settings.TUTOR_VIDEO_MAX_UPLOAD_BYTES)
    digest = hashlib.sha256()
    size = 0
    prefix = b""
    upload.seek(0)
    for chunk in upload.chunks():
        size += len(chunk)
        if size > limit:
            raise ValidationError("The video exceeds the upload size limit.")
        if len(prefix) < 4096:
            prefix += chunk[: 4096 - len(prefix)]
        digest.update(chunk)
    upload.seek(0)
    valid = (prefix.startswith(b"\x1aE\xdf\xa3") and b"webm" in prefix) if suffix == ".webm" else prefix[4:8] == b"ftyp"
    if not size or not valid:
        raise ValidationError("The file does not have a supported video container header.")
    return {
        "file_name": name,
        "file_size": size,
        "content_type": types[suffix],
        "sha256": digest.hexdigest(),
        "suffix": suffix,
    }


def admin_recipient():
    site = SiteSettings.objects.first()
    value = settings.TUTOR_VIDEO_ADMIN_EMAIL or (site.email if site else DEFAULT_EMAIL)
    validate_email(value)
    return value


def _snapshot(video, tutor, details, kind):
    origin = urlsplit(getattr(settings, "PUBLIC_API_URL", ""))
    review_url = ""
    if origin.scheme == "https" and origin.netloc and not origin.username and not origin.password:
        review_url = f"https://{origin.netloc}/admin/content/videoasset/{video.pk}/change/"
    return {
        "tutor_name": tutor.get_full_name().strip() or tutor.get_username(),
        "tutor_email": tutor.email,
        "title": video.title,
        "curriculum": video.get_curriculum_display() or "Not provided",
        "subject": video.get_subject_display() or "Not provided",
        "level": video.academic_level or "Not provided",
        "topic": video.topic or "Not provided",
        "provider": video.get_provider_display(),
        "activity": kind,
        "file_name": details.get("file_name", "Not applicable"),
        "file_size": details.get("file_size", 0),
        "duration_seconds": video.duration_seconds,
        "uploaded_at": timezone.now()
        .astimezone(ZoneInfo("Africa/Johannesburg"))
        .strftime("%A, %d %B %Y at %H:%M:%S SAST (UTC+2)"),
        "review_url": review_url,
        "publication": "Published" if video.is_live else "Draft / pending Admin review",
    }


def record_upload(video, tutor, key, fingerprint, details, kind):
    return TutorVideoUpload.objects.create(
        video=video,
        tutor=tutor,
        idempotency_key=key,
        fingerprint=fingerprint,
        recipient=admin_recipient(),
        payload=_snapshot(video, tutor, details, kind),
    )


@transaction.atomic
def save_admin_video(video, actor, form, change, save):
    """Capture successful media changes in the existing Django Admin upload path."""
    if not approved_tutor(actor):
        if not change:
            video.uploaded_by = actor
        save()
        return
    if change and video.uploaded_by_id != actor.pk and not actor.is_superuser:
        raise ValidationError("Only your own video can be changed.")
    media_fields = {"source_file", "youtube_video_id", "youtube_url", "provider"}
    changed = not change or bool(media_fields.intersection(form.changed_data))
    details = {}
    if changed and video.provider == "s3" and video.source_file and not video.source_file._committed:
        details = inspect_video(video.source_file.file)
        fingerprint = details["sha256"]
        kind = "Video replaced" if change else "New video uploaded"
    elif changed and video.provider == "youtube":
        fingerprint = hashlib.sha256(video.youtube_video_id.encode()).hexdigest()
        kind = "Private YouTube video registered"
    else:
        save()
        return
    if not change:
        video.uploaded_by = actor
    if not actor.is_superuser:
        video.is_published, video.publish_at, video.allow_preview = False, None, False
    save()
    record_upload(video, actor, str(uuid.uuid4()), fingerprint, details, kind)


def submit_video(*, tutor, key, upload, metadata, video_id=None):
    if not approved_tutor(tutor):
        raise ValidationError("Approved tutor access is required.")
    details = inspect_video(upload)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"metadata": metadata, "target": str(video_id or ""), "sha256": details["sha256"]}, sort_keys=True
        ).encode()
    ).hexdigest()
    existing = TutorVideoUpload.objects.filter(tutor=tutor, idempotency_key=key).first()
    if existing:
        if existing.fingerprint != fingerprint:
            raise UploadConflict("This upload key belongs to a different video or set of details.")
        return existing, False
    if video_id and not VideoAsset.objects.filter(pk=video_id, uploaded_by=tutor, is_published=False).exists():
        raise UploadConflict("Only your own unpublished video may be replaced.")
    storage = VideoAsset._meta.get_field("source_file").storage
    stored = storage.save(f"videos/tutor-uploads/{tutor.pk}/{uuid.uuid4()}{details['suffix']}", upload)
    try:
        with transaction.atomic():
            tutor = get_user_model().objects.select_for_update().get(pk=tutor.pk)
            if not approved_tutor(tutor):
                raise ValidationError("Approved tutor access is required.")
            existing = TutorVideoUpload.objects.filter(tutor=tutor, idempotency_key=key).first()
            if existing:
                if existing.fingerprint != fingerprint:
                    raise UploadConflict("This upload key belongs to another video.")
                event, created = existing, False
            else:
                if video_id:
                    video = VideoAsset.objects.select_for_update().filter(pk=video_id, uploaded_by=tutor).first()
                    if video is None or video.is_published:
                        raise UploadConflict(
                            "Only your own unpublished video may be replaced. Submit a new draft for a published video."
                        )
                else:
                    video = VideoAsset(uploaded_by=tutor)
                for field, value in metadata.items():
                    setattr(video, field, value)
                video.provider = VideoAsset.Provider.S3
                video.youtube_video_id, video.youtube_url = "", ""
                video.source_file = stored
                video.is_published, video.publish_at, video.allow_preview = False, None, False
                video.full_clean()
                video.save()
                event = record_upload(
                    video, tutor, key, fingerprint, details, "Video replaced" if video_id else "New video uploaded"
                )
                created = True
        if not created:
            storage.delete(stored)
        return event, created
    except Exception:
        try:
            storage.delete(stored)
        except Exception:
            logger.warning("tutor_video_private_orphan_cleanup_pending")
        raise


def alert_lines(event):
    p = event.payload
    return [
        "A tutor has successfully submitted a video to the academy. Please review the content in Django Admin.",
        f"Activity: {p['activity']}",
        f"Tutor: {p['tutor_name']}",
        f"Tutor email: {p['tutor_email']}",
        f"Video title: {p['title']}",
        f"Curriculum: {p['curriculum']}",
        f"Subject: {p['subject']}",
        f"Grade / level / module: {p['level']}",
        f"Topic: {p['topic']}",
        f"Provider: {p['provider']}",
        f"Filename: {p['file_name']}",
        f"File size: {p['file_size']:,} bytes ({p['file_size'] / 1048576:.2f} MiB)",
        (
            f"Tutor-reported duration: {p['duration_seconds']} seconds"
            if p["duration_seconds"]
            else "Duration: not supplied"
        ),
        f"Upload time: {p['uploaded_at']}",
        f"Publication status at upload: {p['publication']}",
        f"Video reference: {event.video_id}",
        f"Activity reference: {event.pk}",
        (
            f"Review in Django Admin: {p['review_url']}"
            if p["review_url"]
            else "Review this video in Django Admin using its video reference."
        ),
        "Open the video securely in Django Admin. Publication requires academy review.",
    ]


def deliver_alert(event_id):
    with transaction.atomic():
        event = TutorVideoUpload.objects.select_for_update().get(pk=event_id)
        if event.delivery_status != "queued" or (event.next_attempt_at and event.next_attempt_at > timezone.now()):
            return 0
        if event.recipient != admin_recipient():
            event.delivery_status, event.error_code = "review", "admin_recipient_changed"
            event.save(update_fields=["delivery_status", "error_code", "updated_at"])
            return 0
        lines = alert_lines(event)
        email = EmailMultiAlternatives(
            subject=f"Amaris tutor video upload - {event.pk}", body="\n\n".join(lines), to=[event.recipient]
        )
        apply_letterhead(email, "Tutor video upload activity", lines, reference=str(event.pk))
        event.delivery_status, event.sending_at = "sending", timezone.now()
        event.attempts += 1
        event.save(update_fields=["delivery_status", "sending_at", "attempts", "updated_at"])
    try:
        sent = email.send(fail_silently=False)
    except (SMTPAuthenticationError, SMTPConnectError, SMTPDataError, SMTPRecipientsRefused, SMTPSenderRefused):
        _failed(event, known_rejected=True, code="smtp_rejected")
        return 0
    except Exception:
        _failed(event, known_rejected=False, code="smtp_outcome_unknown")
        return 0
    if sent != 1:
        _failed(event, known_rejected=True, code="mail_not_accepted")
        return 0
    TutorVideoUpload.objects.filter(pk=event.pk, delivery_status="sending").update(
        delivery_status="sent", sent_at=timezone.now(), error_code=""
    )
    return 1


def _failed(event, *, known_rejected, code):
    retry = known_rejected and event.attempts < 5
    TutorVideoUpload.objects.filter(pk=event.pk, delivery_status="sending").update(
        delivery_status="queued" if retry else "review",
        error_code=code,
        next_attempt_at=timezone.now() + timedelta(minutes=2**event.attempts) if retry else None,
    )

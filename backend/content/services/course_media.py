"""Direct uploads and protected playback for academy course media."""

import json
import re
import uuid
from pathlib import PurePath
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.core.files.storage import Storage, default_storage, storages

PREFIX = "academy-media/"
FOLDER_URL = "https://vimeo.com/user/261260024/folder/31427264"
FOLDER = "/users/261260024/projects/31427264"
S3_FORMATS = {".mp4": "video/mp4", ".webm": "video/webm", ".m4v": "video/mp4"}
VIMEO_FORMATS = {*S3_FORMATS, ".mov", ".mkv", ".avi", ".wmv", ".mpeg", ".mpg", ".mxf", ".3gp", ".flv", ".ogv", ".ts"}
MAX_BYTES = 4 * 1024**3
VIDEO_URI = re.compile(r"/videos/([1-9][0-9]{0,18})", re.ASCII)


class CourseFileStorage(Storage):
    """Route new course files to AWS and keep legacy names on their original storage."""

    def _backend(self, name):
        return storages["academy_media"] if name.startswith(PREFIX) else default_storage

    def save(self, name, content, max_length=None):
        if settings.ACADEMY_MEDIA_BUCKET:
            name = PREFIX + name
        return self._backend(name).save(name, content, max_length=max_length)

    def _open(self, name, mode="rb"):
        return self._backend(name).open(name, mode)

    def exists(self, name):
        return self._backend(name).exists(name)

    def size(self, name):
        return self._backend(name).size(name)

    def delete(self, name):
        return self._backend(name).delete(name)

    def url(self, name):
        return self._backend(name).url(name)

    def deconstruct(self):
        return "content.services.course_media.CourseFileStorage", (), {}


course_files = CourseFileStorage()


def enabled_providers():
    return {
        "s3": bool(settings.ACADEMY_MEDIA_BUCKET),
        "vimeo": bool(settings.ACADEMY_VIMEO_TOKEN and settings.ACADEMY_VIMEO_EMBED_DOMAINS),
    }


def s3_client():
    return boto3.client(
        "s3",
        region_name=settings.ACADEMY_MEDIA_REGION,
        config=Config(signature_version="s3v4", request_checksum_calculation="when_required"),
    )


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def _vimeo(path, method="GET", payload=None):
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError("Invalid Vimeo API path")
    req = Request(
        f"https://api.vimeo.com{path}",
        method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "Authorization": f"Bearer {settings.ACADEMY_VIMEO_TOKEN}",
            "Accept": "application/vnd.vimeo.*+json;version=3.4",
            "Content-Type": "application/json",
        },
    )
    with build_opener(_NoRedirect()).open(req, timeout=12) as response:
        raw = response.read(1_000_000)
        return json.loads(raw) if raw else {}


def _begin_vimeo(title, size):
    _vimeo(FOLDER)
    video = _vimeo(
        "/me/videos",
        "POST",
        {
            "name": title,
            "upload": {"approach": "tus", "size": str(size)},
            "folder_uri": FOLDER,
            "privacy": {"view": "disable", "embed": "whitelist", "download": False},
        },
    )
    uri = video.get("uri", "")
    match = VIDEO_URI.fullmatch(uri)
    if not match:
        raise ValidationError("Vimeo returned an invalid video reference.")
    link = video.get("upload", {}).get("upload_link", "")
    parsed = urlsplit(link)
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or not parsed.hostname
        or not parsed.hostname.endswith(".vimeo.com")
    ):
        raise ValidationError("Vimeo returned an invalid upload address.")
    for domain in settings.ACADEMY_VIMEO_EMBED_DOMAINS:
        _vimeo(f"{uri}/privacy/domains/{quote(domain, safe='')}", "PUT")
    return {"url": link}, match.group(1)


def begin_video_upload(*, user_id, asset_id, provider, filename, size, title):
    if not enabled_providers().get(provider):
        raise ValidationError("This upload provider is unavailable.")
    if isinstance(size, bool) or not isinstance(size, int) or not 0 < size <= MAX_BYTES:
        raise ValidationError("Select a non-empty video file up to 4 GiB.")
    suffix = PurePath(filename).suffix.lower()
    if provider == "s3":
        if suffix not in S3_FORMATS:
            raise ValidationError("Select an MP4, M4V or WebM file for S3 playback.")
        mime = S3_FORMATS[suffix]
        reference = f"{PREFIX}videos/{uuid.uuid4().hex}{suffix}"
        url = s3_client().generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.ACADEMY_MEDIA_BUCKET,
                "Key": reference,
                "ContentType": mime,
                "ContentLength": size,
                "ServerSideEncryption": "AES256",
                "IfNoneMatch": "*",
            },
            ExpiresIn=1800,
        )
        post = {
            "url": url,
            "headers": {"Content-Type": mime, "x-amz-server-side-encryption": "AES256", "If-None-Match": "*"},
        }
    else:
        if suffix not in VIMEO_FORMATS:
            raise ValidationError("Select a supported video file for Vimeo.")
        post, reference = _begin_vimeo(title, size)
    ticket = signing.dumps(
        {"admin": str(user_id), "asset": str(asset_id), "provider": provider, "ref": reference, "size": size},
        salt="academy-video-upload",
    )
    return {**post, "ticket": ticket}


def verify_video_upload(ticket, *, user_id, asset_id, provider):
    try:
        claims = signing.loads(ticket, salt="academy-video-upload", max_age=6 * 3600)
    except signing.BadSignature:
        raise ValidationError("This upload authorization expired. Upload the file again.") from None
    if (
        claims["admin"] != str(user_id)
        or claims["asset"] != str(asset_id)
        or claims["provider"] != provider
        or not enabled_providers().get(provider)
    ):
        raise ValidationError("This upload does not belong to the selected asset and destination.")
    reference = claims["ref"]
    try:
        if provider == "s3":
            obj = s3_client().head_object(Bucket=settings.ACADEMY_MEDIA_BUCKET, Key=reference)
            expected_type = S3_FORMATS[PurePath(reference).suffix]
            if (
                obj["ContentLength"] != claims["size"]
                or obj.get("ContentType") != expected_type
                or obj.get("ServerSideEncryption") != "AES256"
            ):
                raise ValidationError("The file in S3 does not match the authorized upload.")
        else:
            video = _vimeo(f"/videos/{reference}?fields=uri,upload.status,privacy,parent_folder.uri")
            privacy = video.get("privacy") or {}
            if (
                video.get("uri") != f"/videos/{reference}"
                or video.get("upload", {}).get("status") != "complete"
                or privacy.get("view") != "disable"
                or privacy.get("embed") != "whitelist"
                or privacy.get("download") is not False
                or (video.get("parent_folder") or {}).get("uri") != FOLDER
            ):
                raise ValidationError("Vimeo has not confirmed the completed upload and embed restrictions.")
    except (BotoCoreError, ClientError, URLError, TimeoutError, ValueError):
        raise ValidationError(
            "The provider could not verify the file. Wait for the upload to finish and try saving again."
        ) from None
    return reference


def lesson_playback_url(video):
    if video.provider == video.Provider.VIMEO and re.fullmatch(r"[1-9][0-9]{0,18}", video.vimeo_video_id):
        return f"https://player.vimeo.com/video/{video.vimeo_video_id}"
    if video.provider != video.Provider.S3:
        return ""
    try:
        if video.aws_media_key and settings.ACADEMY_MEDIA_BUCKET:
            return storages["academy_media"].url(video.aws_media_key)
        if video.source_file and getattr(video.source_file.storage, "querystring_auth", False):
            return video.source_file.url
    except (BotoCoreError, ClientError):
        return ""
    return ""

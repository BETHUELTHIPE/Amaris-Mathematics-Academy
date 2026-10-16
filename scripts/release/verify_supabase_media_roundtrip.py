"""Disposable, real Supabase S3 media roundtrip; never touches Django production DB.

Intentionally executes on a trusted GitHub Actions main workflow only.
Always cleans up only self-created unique objects, including on partial failure.
"""
import hashlib
import io
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import urlopen

import boto3
from botocore.config import Config
from PIL import Image


BUCKET = "amaris-cms-files"
ENDPOINT = "https://epkcuseloinygkakxxdu.storage.supabase.co/storage/v1/s3"
REGION = "us-east-1"


def make_pdf() -> bytes:
    parts = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 100 100] /Contents 4 0 R >>",
        b"<< /Length 0 >>\nstream\n\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    positions = [0]
    for index, item in enumerate(parts, 1):
        positions.append(len(data))
        data += f"{index} 0 obj\n".encode() + item + b"\nendobj\n"
    off = len(data)
    data += f"xref\n0 {len(positions)}\n0000000000 65535 f \n".encode()
    for position in positions[1:]:
        data += f"{position:010d} 00000 n \n".encode()
    data += f"trailer\n<< /Root 1 0 R /Size {len(positions)} >>\nstartxref\n{off}\n%%EOF\n".encode()
    return bytes(data)


def files() -> dict[str, tuple[bytes, str]]:
    png = io.BytesIO()
    Image.new("RGB", (32, 32), (30, 70, 170)).save(png, format="PNG")
    with tempfile.TemporaryDirectory() as dirname:
        video = Path(dirname) / "smoke.mp4"
        subprocess.run(
            [
                "ffmpeg", "-nostdin", "-v", "error", "-y",
                "-f", "lavfi", "-i", "color=c=blue:s=32x32:d=1",
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart", str(video),
            ], check=True, timeout=25,
        )
        mp4 = video.read_bytes()
    if not mp4.startswith(b"\x00\x00") or b"ftyp" not in mp4[:32]:
        raise RuntimeError("MP4 fixture is invalid")
    return {
        "image.png": (png.getvalue(), "image/png"),
        "video.mp4": (mp4, "video/mp4"),
        "document.pdf": (make_pdf(), "application/pdf"),
    }


def main():
    access = os.environ.get("SUPABASE_STORAGE_S3_ACCESS_KEY_ID")
    secret = os.environ.get("SUPABASE_STORAGE_S3_SECRET_ACCESS_KEY")
    if not access or not secret:
        raise RuntimeError("S3 credential secrets missing; no upload attempted")
    if os.environ.get("GITHUB_REPOSITORY") != "BETHUELTHIPE/Amaris-Mathematics-Academy":
        raise RuntimeError("Unexpected GitHub repository")
    if os.environ.get("GITHUB_REF") != "refs/heads/main":
        raise RuntimeError("Only trusted main may run this S3 test")
    client = boto3.client(
        "s3", endpoint_url=ENDPOINT, region_name=REGION,
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=12,
                      retries={"total_max_attempts": 2}),
    )
    run_id = os.environ.get("GITHUB_RUN_ID", "manual")
    prefix = f"marketing/announcements/staging-smoke/{run_id}-{uuid.uuid4().hex}/"
    created = []
    error = None
    try:
        for name, (raw, content_type) in files().items():
            key = prefix + name
            created.append(key)  # Register before PUT to allow cleanup of partial writes.
            client.put_object(Bucket=BUCKET, Key=key, Body=raw, ContentType=content_type)
            head = client.head_object(Bucket=BUCKET, Key=key)
            if int(head["ContentLength"]) != len(raw):
                raise RuntimeError(f"{name}: upload size mismatch")
            if head.get("ContentType") != content_type:
                raise RuntimeError(f"{name}: MIME type mismatch")
            signed = client.generate_presigned_url(
                "get_object", Params={"Bucket": BUCKET, "Key": key},
                ExpiresIn=120,
            )
            parsed = urlsplit(signed)
            if parsed.scheme != "https" or parsed.hostname != urlsplit(ENDPOINT).hostname:
                raise RuntimeError(f"{name}: unexpected signed URL host")
            query = parse_qs(parsed.query)
            if query.get("X-Amz-Expires") != ["120"] or not query.get("X-Amz-Signature"):
                raise RuntimeError(f"{name}: invalid signed URL expiry/signature")
            with urlopen(signed, timeout=15) as response:
                got = response.read()
            if hashlib.sha256(got).digest() != hashlib.sha256(raw).digest():
                raise RuntimeError(f"{name}: signed download hash mismatch")
            print(f"PASS {name}: S3 PUT, HEAD, 120s signed HTTPS GET, SHA256 exact")
    except Exception as exc:
        error = exc
        print(f"FAIL {type(exc).__name__}: {str(exc)[:160]}")
    finally:
        cleanup_error = None
        for key in created:
            try:
                client.delete_object(Bucket=BUCKET, Key=key)
            except Exception as exc:
                cleanup_error = type(exc).__name__
        try:
            remaining = client.list_objects_v2(Bucket=BUCKET, Prefix=prefix, MaxKeys=10).get("KeyCount", 0)
            if remaining:
                cleanup_error = "objects remain"
        except Exception as exc:
            cleanup_error = type(exc).__name__
        if cleanup_error:
            print(f"FAIL cleanup: {cleanup_error}; review test prefix in the CMS bucket")
            raise RuntimeError("Test S3 cleanup not verified")
        print("PASS cleanup: disposable files removed from CMS bucket")
    if error:
        raise RuntimeError("Media S3 roundtrip did not pass") from error
    print("PASS all real Supabase S3 image/video/PDF tests")


if __name__ == "__main__":
    main()

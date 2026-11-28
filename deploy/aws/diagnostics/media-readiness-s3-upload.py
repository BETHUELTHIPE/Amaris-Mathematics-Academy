"""Exercise the staging tutor API with a disposable private S3 video."""
import base64
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

ORIGIN = "https://16.171.164.5"
EXPECTED_HOST = "amaris-mathematics-academy-media-stage-110156539003-eu-north-1.s3.eu-north-1.amazonaws.com"
QA_HASH = "2351cb430f5976021719b1c7fb36bd3ec0559d79a32b694c38b7f4a0313bb03a"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


http = build_opener(NoRedirect())
fixture = Path(os.environ["RUNNER_TEMP"]) / "tutor-video-probe.json"
details = {}


def request(url, *, method="GET", data=None, headers=None):
    kwargs = {"headers": {"Accept": "application/json", **(headers or {})}, "method": method}
    if data is not None:
        kwargs["headers"]["Content-Type"] = "application/json"
        kwargs["data"] = json.dumps(data).encode()
    with http.open(Request(url, **kwargs), timeout=18) as response:
        return json.load(response), response.headers


def expect_denial(url, **kwargs):
    try:
        request(url, **kwargs)
    except HTTPError as exc:
        assert exc.code in (401, 403), f"Expected auth denial, received HTTP {exc.code}"
    else:
        raise AssertionError("A tutor endpoint accepted an anonymous request")


def save_fixture():
    fixture.write_text(json.dumps(details))


def main():
    expect_denial(f"{ORIGIN}/api/v1/tutor/videos/")
    expect_denial(
        f"{ORIGIN}/api/tutor-videos", method="POST", data={"action": "start"}, headers={"Origin": ORIGIN}
    )
    expect_denial(f"{ORIGIN}/api/tutor-videos", method="POST", data={"action": "start"},
                  headers={"Origin": "https://different-origin.example"})
    email = os.environ["STAGING_TEST_TUTOR_EMAIL"].strip().lower()
    assert hashlib.sha256(email.encode()).hexdigest() == QA_HASH
    session, _ = request(
        "https://atyhhjwwxgzeurnwayay.supabase.co/auth/v1/token?" + urlencode({"grant_type": "password"}),
        method="POST", headers={"apikey": os.environ["STAGING_SUPABASE_PUBLISHABLE_KEY"]},
        data={"email": email, "password": os.environ["STAGING_TEST_TUTOR_PASSWORD"]},
    )
    assert session["user"]["email"].lower() == email and session["user"]["email_confirmed_at"]
    # Use the cookie format of the installed @supabase/ssr client with the
    # newly issued real staging session. Never print the cookie or its value.
    session.setdefault("expires_at", int(time.time()) + session["expires_in"])
    encoded = base64.urlsafe_b64encode(json.dumps(session, separators=(",", ":")).encode()).decode().rstrip("=")
    value = "base64-" + encoded
    cookie_name = "sb-atyhhjwwxgzeurnwayay-auth-token"
    if len(value) <= 3180:
        cookie = f"{cookie_name}={value}"
    else:
        cookie = "; ".join(
            f"{cookie_name}.{i // 3180}={value[i:i + 3180]}" for i in range(0, len(value), 3180)
        )
    browser_headers = {"Cookie": cookie, "Origin": ORIGIN}
    with http.open(Request(f"{ORIGIN}/tutor/dashboard", headers={"Cookie": cookie}), timeout=25) as response:
        page = response.read()
        assert response.status == 200 and b"Lesson videos" in page and b"Upload for review" in page
    print("Confirmed the authenticated tutor dashboard renders the upload form.")
    auth = {"Authorization": f'Bearer {session["access_token"]}'}
    videos = f"{ORIGIN}/api/v1/tutor/videos/"
    initial, headers = request(videos, headers=auth)
    assert initial["providers"]["s3"] is True and headers["Cache-Control"] == "private, no-store"

    with tempfile.TemporaryDirectory() as directory:
        video = Path(directory, "fixture.mp4")
        subprocess.run(
            ["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)], check=True, timeout=20
        )
        body = video.read_bytes()
    print(f"Live provider availability: S3={initial['providers']['s3']}, Vimeo={initial['providers']['vimeo']}.", flush=True)
    title = f"Staging tutor upload probe {uuid.uuid4().hex}"
    start, _ = request(f"{ORIGIN}/api/tutor-videos", method="POST", headers=browser_headers,
                       data={"action":"start","provider":"s3","title":title,"filename":"fixture.mp4","size":len(body)})
    url = urlsplit(start["url"])
    assert url.scheme == "https" and url.hostname == EXPECTED_HOST
    key = url.path.lstrip("/")
    assert re.fullmatch(r"academy-media/videos/[a-f0-9]{32}\.mp4", key)
    assert str(uuid.UUID(start["submission"])) == start["submission"]
    details.update(id=start["submission"], title=title, key=key)
    save_fixture()

    preflight = Request(start["url"], method="OPTIONS", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": ", ".join(start["headers"]).lower(),
    })
    with http.open(preflight, timeout=16) as response:
        assert response.status == 200 and response.headers["Access-Control-Allow-Origin"] == ORIGIN
        assert "PUT" in response.headers["Access-Control-Allow-Methods"]
        allowed = {h.strip().lower() for h in response.headers["Access-Control-Allow-Headers"].split(",")}
        assert "*" in allowed or set(map(str.lower, start["headers"])) <= allowed

    payload = {"action":"finish","provider":"s3","ticket":start["ticket"],"submission":start["submission"]}
    try:
        request(f"{ORIGIN}/api/tutor-videos", method="POST", headers=browser_headers, data=payload)
    except HTTPError as error:
        assert error.code == 400, f"Missing-file completion returned HTTP {error.code}."
    else:
        raise AssertionError("Completion accepted a file that had not been uploaded.")

    put = Request(start["url"], method="PUT", data=body, headers={**start["headers"], "Origin": ORIGIN})
    with http.open(put, timeout=20) as response:
        details["version"] = response.headers["x-amz-version-id"]
        save_fixture()
        assert response.status == 200 and response.headers["Access-Control-Allow-Origin"] == ORIGIN

    try:
        http.open(put, timeout=20).close()
    except HTTPError as error:
        assert error.code == 412, f"Duplicate upload returned HTTP {error.code}."
    else:
        raise AssertionError("The existing S3 object could be overwritten.")
    expect_denial(url._replace(query="").geturl())
    print("Verified CORS preflight, rejected a missing upload and duplicate PUT, and denied unsigned access.")
    result, headers = request(f"{ORIGIN}/api/tutor-videos", method="POST", headers=browser_headers, data=payload)
    assert result == {"id":start["submission"], "title":title, "provider":"s3", "ready":False}
    assert headers["Cache-Control"] == "private, no-store"
    repeat, _ = request(f"{ORIGIN}/api/tutor-videos", method="POST", headers=browser_headers, data=payload)
    assert repeat == result
    own, _ = request(videos, headers=auth)
    assert sum(video == result for video in own["videos"]) == 1
    print("Verified a real approved tutor, private MP4 upload, unpublished draft, idempotent retry and tutor-owned list.")
    print(f"Provider availability in the live tutor dashboard: S3={initial['providers']['s3']}, Vimeo={initial['providers']['vimeo']}.")


try:
    main()
except HTTPError as error:
    raise SystemExit(f"The staging verification request returned HTTP {error.code}.") from None

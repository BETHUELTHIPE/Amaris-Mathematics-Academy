"""Validate announcement links and discard YouTube Studio/tracking parameters."""

import re
from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import ValidationError

ERROR = "Enter an HTTPS YouTube video or playlist link, including a valid video or playlist ID."
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
PLAYLIST_ID = re.compile(r"[A-Za-z0-9_-]{10,128}\Z")


def normalise_youtube_url(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in value) or "\\" in value:
        raise ValidationError(ERROR)
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username is not None or parsed.password is not None or parsed.port:
            raise ValueError
        host = parsed.hostname
        parts = parsed.path.strip("/").split("/")
        query = parse_qs(parsed.query)
        video = ""
        playlist = ""
        if host == "youtu.be" and len(parts) == 1:
            video = parts[0]
        elif host == "studio.youtube.com" and len(parts) == 3:
            if parts[0] == "playlist" and parts[2] == "videos":
                playlist = parts[1]
            elif parts[0] == "video" and parts[2] == "edit":
                video = parts[1]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "www.youtube-nocookie.com"}:
            if parts == ["watch"]:
                video = query.get("v", [""])[0]
            elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"} and parts[1] != "videoseries":
                video = parts[1]
            elif parts in (["playlist"], ["embed"], ["embed", "videoseries"]):
                playlist = query.get("list", [""])[0]
        if video and VIDEO_ID.fullmatch(video):
            return f"https://www.youtube.com/watch?v={video}"
        if playlist and PLAYLIST_ID.fullmatch(playlist):
            return f"https://www.youtube.com/playlist?list={playlist}"
    except ValueError:
        pass
    raise ValidationError(ERROR)

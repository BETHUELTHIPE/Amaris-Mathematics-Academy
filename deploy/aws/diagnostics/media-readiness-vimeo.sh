#!/usr/bin/env bash
set -euo pipefail
task="$1"
[[ "$task" =~ ^[a-f0-9]{32}$ ]]
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task" --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$backend" python - <<'PY'
import json
import os
from pathlib import Path
from urllib.error import HTTPError, URLError

for entry in Path("/proc/1/environ").read_bytes().split(b"\0"):
    if entry:
        name, _, value = os.fsdecode(entry).partition("=")
        os.environ[name] = value
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()
from django.conf import settings
from content.services.course_media import FOLDER, _vimeo, enabled_providers

assert settings.SUPABASE_PROJECT_REF == "atyhhjwwxgzeurnwayay"
token_set = bool(settings.ACADEMY_VIMEO_TOKEN)
print(json.dumps({
    "vimeo_enabled": enabled_providers()["vimeo"],
    "vimeo_token_present": token_set,
    "vimeo_embed_domains_configured": bool(settings.ACADEMY_VIMEO_EMBED_DOMAINS),
    "staging_origin_allowlisted": "16.171.164.5" in settings.ACADEMY_VIMEO_EMBED_DOMAINS,
}), flush=True)
if token_set:
    try:
        folder = _vimeo(FOLDER + "?fields=uri")
        print(f"Vimeo approved folder API accessible and matching: {folder.get('uri') == FOLDER}.")
    except HTTPError as exc:
        print(f"Vimeo folder API returned HTTP {exc.code}.")
    except (URLError, OSError, TimeoutError, ValueError):
        print("Vimeo folder API could not be reached or did not return expected metadata.")
else:
    print("The running application cannot authenticate to the Vimeo folder.")
PY

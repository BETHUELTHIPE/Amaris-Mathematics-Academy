#!/usr/bin/env bash
set -euo pipefail
task="$1"
submission="$2"
nonce="$3"
[[ "$task" =~ ^[a-f0-9]{32}$ && "$submission" =~ ^[a-f0-9-]{36}$ && "$nonce" =~ ^[a-f0-9]{32}$ ]]
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$task"   --filter label=com.amazonaws.ecs.container-name=backend)"
[[ "$backend" =~ ^[a-f0-9]{12,64}$ ]]
docker exec -i "$backend" python - "$submission" "$nonce" <<'PY'
import hashlib
import os
import sys
for line in os.environ.pop("AMARIS_RUNTIME_ENV", "").splitlines():
    name, sep, value = line.partition("=")
    if sep:
        os.environ[name] = value
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()

from django.db import connection, transaction
from content.models import VideoAsset

project = "atyhhjwwxgzeurnwayay"
database = connection.settings_dict
assert database["HOST"] == f"db.{project}.supabase.co" or (
    database["HOST"].endswith(".pooler.supabase.com") and database["USER"].endswith("." + project)
)
submission, nonce = sys.argv[1:3]
with transaction.atomic():
    video = VideoAsset.objects.select_for_update().filter(pk=submission).first()
    if video:
        assert video.title == f"Staging tutor upload probe {nonce}" and video.provider == "s3"
        assert not video.is_published and not video.lessons.exists()
        assert hashlib.sha256(video.submitted_by.email.strip().lower().encode()).hexdigest() == "2351cb430f5976021719b1c7fb36bd3ec0559d79a32b694c38b7f4a0313bb03a"
        video.delete()
print("Verified cleanup of the isolated tutor video draft.")
PY

"""Start an isolated real Django backend with only synthetic runtime bindings."""

import os
import subprocess
import sys

for command in (["migrate", "--noinput"], ["collectstatic", "--noinput"]):
    subprocess.run([sys.executable, "manage.py", *command], check=True)
os.execv(
    sys.executable,
    [sys.executable, "-m", "gunicorn", "-c", "/app/gunicorn.conf.py", "amaris_cms.asgi:application"],
)

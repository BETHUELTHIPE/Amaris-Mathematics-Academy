#!/usr/bin/env bash
set -euo pipefail

[[ "$1" =~ ^[a-f0-9]{32}$ ]]
task="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$1"
backend="$(docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$task" --filter label=com.amazonaws.ecs.container-name=backend)"
if [[ ! "$backend" =~ ^[a-f0-9]{12,64}$ ]]; then
  echo 'Backend container is still starting or has stopped.'
  exit 0
fi
docker exec -i "$backend" python - <<'PY'
import http.client
import json
import os
import re
import socket
import time
from pathlib import Path

for item in Path("/proc/1/environ").read_bytes().split(b"\0"):
    if item:
        key, _, value = os.fsdecode(item).partition("=")
        os.environ[key] = value

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "amaris_cms.settings")
import django
django.setup()
from django.db import connection

known = {
    "max client": "pool-client-limit",
    "too many clients": "postgres-client-limit",
    "remaining connection slots": "postgres-client-limit",
    "pool size": "pool-capacity",
    "pool timeout": "pool-timeout",
    "timed out": "connect-timeout",
    "timeout": "timeout",
    "server closed": "server-closed",
    "connection refused": "connection-refused",
    "connection reset": "connection-reset",
    "network is unreachable": "network-unreachable",
    "could not translate": "dns",
    "temporary failure in name resolution": "dns",
    "authentication failed": "authentication",
    "password authentication failed": "authentication",
    "tenant or user not found": "pool-tenant-or-user",
    "ssl": "tls",
    "unsupported startup": "startup-parameter",
    "prepared statement": "prepared-statement",
}

def failure(error):
    exception = error.__cause__ or error
    original = str(exception).lower()
    labels = sorted({label for marker, label in known.items() if marker in original})
    code = getattr(exception, "sqlstate", "") or ""
    sqlstatus = code if re.fullmatch(r"[0-9A-Z]{5}", code) else "unavailable"
    return type(exception).__name__, sqlstatus, labels

settings = connection.settings_dict
host, port = settings["HOST"], settings["PORT"]
pool = "supabase-pooler" if host.endswith(".pooler.supabase.com") else "other"
print(f"Database endpoint type {pool}, port {port}, connection age {settings['CONN_MAX_AGE']} seconds.")
try:
    addresses = socket.getaddrinfo(host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
    print(f"Database DNS address count {len(set((row[0], row[4][0]) for row in addresses))}.")
except OSError as error:
    print("DNS failure:", failure(error))

def probe(path):
    conn = http.client.HTTPConnection("127.0.0.1", 8000, timeout=12)
    try:
        conn.request("GET", path, headers={"Host": "16.171.164.5", "X-Forwarded-Proto": "https"})
        res = conn.getresponse()
        payload = res.read(65536)
        dependencies = ""
        if path.endswith("/dependencies/"):
            try:
                parsed = json.loads(payload).get("dependencies", {})
                dependencies = f" PostgreSQL={parsed.get('postgresql')!s}, Valkey={parsed.get('redis')!s}"
            except (ValueError, AttributeError):
                pass
        print(f"Django {path} returned {res.status}{dependencies}.")
    except (OSError, http.client.HTTPException) as error:
        print(f"Django {path} failure:", failure(error))
    finally:
        conn.close()

for attempt in range(3):
    probe("/health/live/")
    probe("/health/dependencies/")
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            assert cursor.fetchone() == (1,)
        print("A new Django database connection executed SELECT 1.")
    except Exception as error:
        print("Django database connection failed:", failure(error))
    finally:
        connection.close()
    if attempt < 2:
        time.sleep(2)
PY
docker logs --since 12m --tail 500 "$backend" 2>&1 | awk '
  { line=tolower($0) }
  /OperationalError/ { operational++ }
  line ~ /could not translate|temporary failure in name resolution/ { dns++ }
  line ~ /remaining connection slots|max client|too many clients|pool size|pool timeout/ { capacity++ }
  line ~ /connection timed out|timeout expired|network is unreachable|connection reset|server closed the connection/ { network++ }
  line ~ /authentication failed|tenant or user not found/ { authentication++ }
  END {printf "Recent backend log matches: database errors=%d, DNS=%d, capacity=%d, network=%d, auth=%d.\n", operational,dns,capacity,network,authentication}
' || true

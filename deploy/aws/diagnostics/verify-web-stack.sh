#!/usr/bin/env bash
set -euo pipefail

if [[ "$1" == gateway ]]; then
  docker exec amaris-gateway nginx -t
  config="$(docker exec amaris-gateway nginx -T 2>/dev/null)"
  grep -Eq 'proxy_pass[[:space:]]+http://amaris_public_alb;' <<< "$config"
  grep -Eq 'listen[[:space:]]+443[[:space:]]+ssl([[:space:]]|;)' <<< "$config"
  printf 'Public Nginx %s proxies HTTPS requests to the ALB.\n' "$(docker exec amaris-gateway nginx -v 2>&1)"
  exit 0
fi

[[ "$1" == task && "$2" =~ ^[a-f0-9]{32}$ ]]
task="arn:aws:ecs:eu-north-1:110156539003:task/amaris-ecs-staging/$2"
get_container() {
  docker ps -q --filter "label=com.amazonaws.ecs.task-arn=$task" \
    --filter "label=com.amazonaws.ecs.container-name=$1"
}

proxy="$(get_container cms)"
backend="$(get_container backend)"
frontend="$(get_container frontend)"
for container in "$proxy" "$backend" "$frontend"; do
  [[ "$container" =~ ^[a-f0-9]{12,64}$ ]] || { echo "Missing running ECS proxy, backend, or frontend container." >&2; exit 1; }
done
docker exec "$proxy" nginx -t
config="$(docker exec "$proxy" nginx -T 2>/dev/null)"
grep -Eq 'listen[[:space:]]+8080 default_server;' <<< "$config"
grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:3000;' <<< "$config"
grep -Eq 'proxy_pass[[:space:]]+http://127\.0\.0\.1:8000;' <<< "$config"
printf 'ECS task Nginx %s is configured for frontend port 3000 and backend port 8000.\n' "$(docker exec "$proxy" nginx -v 2>&1)"

docker exec -i "$backend" python - <<'PY'
import http.client
import json
import runpy
from importlib.metadata import version
from pathlib import Path


def request(port, path):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        connection.request("GET", path, headers={"Host": "16.171.164.5", "X-Forwarded-Proto": "https"})
        response = connection.getresponse()
        assert response.status == 200, f"Port {port} at {path} returned {response.status}."
        return response.getheader("Server", ""), response.read(2_000_000)
    finally:
        connection.close()


pid = Path("/proc/1")
command = (pid / "cmdline").read_bytes().replace(b"\0", b" ")
assert b"gunicorn" in command and b"amaris_cms.asgi:application" in command, "Gunicorn is not running as the ASGI master."
configuration = runpy.run_path("/app/gunicorn.conf.py")
assert configuration["worker_class"] == "amaris_cms.workers.PrivacyUvicornWorker", "Unexpected Gunicorn worker class."
children = (pid / "task/1/children").read_text().split()
assert children, "Gunicorn has no live worker processes."

server, body = request(8000, "/health/live/")
assert "uvicorn" in server.lower() and json.loads(body)["status"] == "ok", "Uvicorn did not serve the Django health response."
print(f"Gunicorn {version('gunicorn')} runs {len(children)} worker process(es), and Uvicorn {version('uvicorn')} served Django over ASGI.")

_, home = request(8080, "/")
assert b"Amaris Mathematics Academy" in home, "Nginx did not serve the Amaris frontend."
_, api = request(8080, "/api/v1/bootstrap/")
assert "settings" in json.loads(api), "Nginx did not serve the Django API."
print("ECS task Nginx served both the frontend homepage and Django API.")
PY

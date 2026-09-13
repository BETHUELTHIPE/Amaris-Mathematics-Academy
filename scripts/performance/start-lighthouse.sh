#!/bin/sh
set -eu

log_file=${LIGHTHOUSE_SERVER_LOG:-/tmp/amaris-lighthouse-server.log}

npm run dev:ci >"$log_file" 2>&1 &
server_pid=$!

cleanup() {
    kill "$server_pid" 2>/dev/null || true
    wait "$server_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

attempt=1
while [ "$attempt" -le 60 ]; do
    if curl --fail --silent http://127.0.0.1:3000/ >/dev/null; then
        break
    fi
    if ! kill -0 "$server_pid" 2>/dev/null; then
        sed -n '1,240p' "$log_file" >&2
        exit 1
    fi
    sleep 1
    attempt=$((attempt + 1))
done

if [ "$attempt" -gt 60 ]; then
    sed -n '1,240p' "$log_file" >&2
    exit 1
fi

# Warm every audited route so Vite dependency optimisation is not counted as
# application performance. Production performance remains enforced by the
# Lighthouse budgets; this removes a development-server-only cold-start cost.
for route in / /courses /contact; do
    curl --fail --silent "http://127.0.0.1:3000$route" >/dev/null
done

echo "LIGHTHOUSE_READY"
wait "$server_pid"

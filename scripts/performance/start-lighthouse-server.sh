#!/usr/bin/env bash
set -euo pipefail

preview_log="${TMPDIR:-/tmp}/amaris-vite-preview.log"

./node_modules/.bin/vite preview --host 127.0.0.1 --port 4173 >"${preview_log}" 2>&1 &
preview_pid=$!
proxy_pid=""

cleanup() {
  if [[ -n "${proxy_pid}" ]]; then
    kill "${proxy_pid}" 2>/dev/null || true
  fi
  kill "${preview_pid}" 2>/dev/null || true
  wait "${proxy_pid}" 2>/dev/null || true
  wait "${preview_pid}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:4173/ >/dev/null; then
    break
  fi
  if [[ "${attempt}" -eq 30 ]]; then
    cat "${preview_log}" >&2
    exit 1
  fi
  sleep 1
done

node scripts/performance/lighthouse-compression-proxy.mjs &
proxy_pid=$!

for attempt in {1..30}; do
  if curl --fail --silent --compressed http://127.0.0.1:4180/ >/dev/null; then
    echo "Lighthouse production-like server ready at http://127.0.0.1:4180"
    wait "${proxy_pid}"
    exit $?
  fi
  if [[ "${attempt}" -eq 30 ]]; then
    echo "Compression proxy did not become ready." >&2
    exit 1
  fi
  sleep 1
done

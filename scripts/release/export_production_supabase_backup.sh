#!/usr/bin/env bash
# Run on a trusted operator workstation, NOT in CI and NOT from a PR runner.
# Required: Supabase CLI, Docker, age, tar, sha256sum, python3.
set -euo pipefail
set +x
umask 077

: "${SUPABASE_PRODUCTION_DATABASE_URL:?Set the private production DB URL via your secret manager.}"
: "${AMARIS_BACKUP_AGE_RECIPIENT:?Provide an age public recipient (keep the private key offline).}"
: "${AMARIS_BACKUP_OUTPUT_DIR:?Choose a private absolute backup directory outside Git.}"

for cmd in supabase age tar sha256sum python3 mktemp; do
  command -v "$cmd" >/dev/null || { echo "Missing backup dependency: $cmd" >&2; exit 1; }
done

python3 - <<'PY'
import os
from pathlib import Path
from urllib.parse import urlsplit

ref = "epkcuseloinygkakxxdu"
url = urlsplit(os.environ["SUPABASE_PRODUCTION_DATABASE_URL"])
hostname = (url.hostname or "").lower()
username = url.username or ""
direct = hostname == f"db.{ref}.supabase.com" and username == "postgres"
pooler = hostname.endswith(".pooler.supabase.com") and username == f"postgres.{ref}"
if url.scheme not in {"postgresql", "postgres"} or not (direct or pooler):
    raise SystemExit("Backup blocked: source URL is not the expected production Supabase project.")
if url.path.rstrip("/") != "/postgres":
    raise SystemExit("Backup blocked: expected the production postgres database.")
destination = Path(os.environ["AMARIS_BACKUP_OUTPUT_DIR"]).expanduser().resolve()
repo_root = Path.cwd().resolve()
if destination == repo_root or repo_root in destination.parents:
    raise SystemExit("Backup blocked: output directory must be outside the Git repository.")
if not destination.is_absolute():
    raise SystemExit("Backup blocked: backup directory must be absolute.")
PY

mkdir -p "$AMARIS_BACKUP_OUTPUT_DIR"
scratch="$(mktemp -d)"
cleanup() {
  rm -rf -- "$scratch"
}
trap cleanup EXIT HUP INT TERM

# Follow Supabase's supported database export method; never echo the DB URL.
supabase db dump --db-url "$SUPABASE_PRODUCTION_DATABASE_URL" -f "$scratch/roles.sql" --role-only
supabase db dump --db-url "$SUPABASE_PRODUCTION_DATABASE_URL" -f "$scratch/schema.sql"
supabase db dump --db-url "$SUPABASE_PRODUCTION_DATABASE_URL" -f "$scratch/data.sql" --use-copy --data-only -x "storage.buckets_vectors" -x "storage.vector_indexes"

for file in roles.sql schema.sql data.sql; do
  test -s "$scratch/$file" || { echo "Backup failed: missing $file" >&2; exit 1; }
done
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
output="$AMARIS_BACKUP_OUTPUT_DIR/amaris-production-supabase-$timestamp.tar.age"
if [ -e "$output" ]; then
  echo "Backup blocked: refusing to overwrite an existing archive." >&2
  exit 1
fi
tar -C "$scratch" -cf - roles.sql schema.sql data.sql | age -r "$AMARIS_BACKUP_AGE_RECIPIENT" -o "$output"
test -s "$output"
sha256sum "$output" > "$output.sha256"
chmod 600 "$output" "$output.sha256"

echo "Encrypted production export produced: $output"
echo "Checksum file: $output.sha256"
echo "NOT RESTORE-VERIFIED. Restore into a separately identified, isolated Supabase project."
echo "Storage bucket objects are NOT contained in this database export."

#!/usr/bin/env bash
# Run AFTER an operator has restored the encrypted export into a SEPARATE project.
# This performs no restore, migration, table writes, or changes to production.
set -euo pipefail
set +x
umask 077

: "${AMARIS_RESTORE_DATABASE_URL:?Set the restored TARGET connection string securely.}"
: "${AMARIS_RESTORE_PROJECT_REF:?Provide the separate TARGET Supabase project reference.}"
test "$AMARIS_RESTORE_PROJECT_REF" != "epkcuseloinygkakxxdu" || {
  echo "Verification blocked: target is the production Supabase project." >&2
  exit 1
}

python3 - <<'PY'
import os
from urllib.parse import urlsplit

ref = os.environ["AMARIS_RESTORE_PROJECT_REF"]
url = urlsplit(os.environ["AMARIS_RESTORE_DATABASE_URL"])
hostname = (url.hostname or "").lower()
user = url.username or ""
direct = hostname == f"db.{ref}.supabase.com" and user == "postgres"
pooler = hostname.endswith(".pooler.supabase.com") and user == f"postgres.{ref}"
if not (direct or pooler) or url.scheme not in {"postgresql", "postgres"}:
    raise SystemExit("Refusing query: target database URL does not match the separate restore project.")
if url.path.rstrip("/") != "/postgres":
    raise SystemExit("Refusing query: expected a separate postgres database.")
PY

# Session read-only mode is enforced within the SQL transaction; avoid writing
# or applying migrations. Only structural facts and aggregate counts are output.
psql "$AMARIS_RESTORE_DATABASE_URL" -X -v ON_ERROR_STOP=1 -At <<'SQL'
BEGIN TRANSACTION READ ONLY;
DO $$
BEGIN
  IF to_regclass('public.django_migrations') IS NULL
      OR to_regclass('public.content_payment') IS NULL
      OR to_regclass('public.content_liveclassbooking') IS NULL
      OR to_regclass('public.content_videorequest') IS NULL
      OR to_regclass('auth.users') IS NULL THEN
    RAISE EXCEPTION 'Expected restored Django/Auth tables are missing';
  END IF;
  IF NOT EXISTS(SELECT 1 FROM public.django_migrations
                WHERE app='content' AND name='0012_tutor_recruitment') THEN
    RAISE EXCEPTION 'Restored database is missing the production content migration baseline';
  END IF;
END $$;
SELECT 'payment_rows=' || COUNT(*) FROM public.content_payment;
SELECT 'live_class_booking_rows=' || COUNT(*) FROM public.content_liveclassbooking;
SELECT 'video_request_rows=' || COUNT(*) FROM public.content_videorequest;
ROLLBACK;
SQL

echo "Isolated restore structural verification passed; compare counts with source and test app recovery."
echo "This verifier does not restore Supabase Storage bucket object bytes."

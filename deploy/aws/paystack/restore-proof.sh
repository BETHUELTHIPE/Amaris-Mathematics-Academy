#!/usr/bin/env bash
set -euo pipefail
umask 077
root="$RUNNER_TEMP/amaris-paystack-recovery"
test -s "$root/app.dump"
docker run -d --name amaris-paystack-recovery-test --network none -e POSTGRES_HOST_AUTH_METHOD=trust postgres:17-alpine >/dev/null
for attempt in {1..40}; do
  if docker exec amaris-paystack-recovery-test pg_isready -U postgres >/dev/null; then break; fi
  sleep 2
done
docker exec amaris-paystack-recovery-test pg_isready -U postgres >/dev/null
docker cp "$root/app.dump" amaris-paystack-recovery-test:/tmp/app.dump >/dev/null
db=amaris-paystack-recovery-test
docker exec "$db" pg_restore -l /tmp/app.dump > "$root/toc" 2>"$root/errors"
# Determine actual schema from the migration table in the archive, not from a guessed default.
schema="$(awk '$4=="TABLE" && $6=="django_migrations" {print $5}' "$root/toc" | sort -u)"
[[ "$schema" =~ ^[A-Za-z_][A-Za-z0-9_]*$ && "$schema" != auth && "$schema" != storage ]]
docker exec "$db" psql -U postgres -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE" >"$root/restore.log" 2>&1
docker exec "$db" pg_restore --exit-on-error --no-owner --no-acl --section=pre-data --section=data -U postgres -d postgres /tmp/app.dump >>"$root/restore.log" 2>&1 || { echo 'BLOCKED: isolated application schema/data restore failed'; exit 1; }
# Only a known external auth FK can be satisfied with an isolated synthetic stub.
if docker exec "$db" psql -U postgres -AtXqc "SELECT to_regclass('$schema.student_profiles') IS NOT NULL" | grep -qx t; then
  docker exec "$db" psql -U postgres -v ON_ERROR_STOP=1 -c "CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid PRIMARY KEY); INSERT INTO auth.users(id) SELECT id FROM \"$schema\".student_profiles ON CONFLICT DO NOTHING; CREATE ROLE anon NOLOGIN; CREATE ROLE authenticated NOLOGIN; CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE RETURN NULL::uuid;" >>"$root/restore.log" 2>&1
fi
docker exec "$db" pg_restore --exit-on-error --no-owner --no-acl --section=post-data -U postgres -d postgres /tmp/app.dump >>"$root/restore.log" 2>&1 || { echo 'BLOCKED: isolated constraints/indexes restore failed'; exit 1; }
docker exec "$db" psql -U postgres -AtXqc "SELECT count(*) > 0 FROM \"$schema\".django_migrations" | grep -qx t
echo 'PASS: genuine staging application schema, data, indexes and constraints restored into network-isolated PostgreSQL 17; Supabase auth/storage remain out of scope.'

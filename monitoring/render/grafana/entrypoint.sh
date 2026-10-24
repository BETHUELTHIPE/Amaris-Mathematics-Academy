#!/bin/sh
set -eu
# Only load a datasource when all connection settings are available.
# Never print credentials. Keep Prometheus available independently.
templates=/etc/amaris/datasource-templates
target=/etc/grafana/provisioning/datasources
if [ -n "${AMARIS_GRAFANA_STAGING_DB_HOSTPORT:-}" ] && [ -n "${AMARIS_GRAFANA_STAGING_DB_USER:-}" ] && [ -n "${AMARIS_GRAFANA_STAGING_DB_PASSWORD:-}" ]; then
  cp "$templates/staging.yml" "$target/amaris-staging.yml"
else
  echo "Amaris staging database: datasource not configured"
fi
if [ -n "${AMARIS_GRAFANA_PRODUCTION_DB_HOSTPORT:-}" ] && [ -n "${AMARIS_GRAFANA_PRODUCTION_DB_USER:-}" ] && [ -n "${AMARIS_GRAFANA_PRODUCTION_DB_PASSWORD:-}" ]; then
  cp "$templates/production.yml" "$target/amaris-production.yml"
else
  echo "Amaris production database: datasource not configured"
fi
exec /run.sh

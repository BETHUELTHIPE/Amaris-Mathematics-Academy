#!/bin/sh
set -eu
: "${AMARIS_DJANGO_TARGET:?Django private hostport is required}"
: "${AMARIS_FLOWER_TARGET:?Flower private hostport is required}"
# Render-controlled host:port values are the only substitutions.
sed -e "s|__DJANGO_TARGET__|${AMARIS_DJANGO_TARGET}|g" \
    -e "s|__FLOWER_TARGET__|${AMARIS_FLOWER_TARGET}|g" \
    /etc/prometheus/prometheus.yml.tmpl > /tmp/prometheus.yml
exec /bin/prometheus \
    --config.file=/tmp/prometheus.yml \
    --web.listen-address=0.0.0.0:${PORT:-10000} \
    --storage.tsdb.path=/prometheus-data \
    --storage.tsdb.retention.time=7d \
    --storage.tsdb.wal-compression \
    --web.enable-lifecycle=false

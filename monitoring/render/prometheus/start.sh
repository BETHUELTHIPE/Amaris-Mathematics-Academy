#!/bin/sh
set -eu

: "${AMARIS_DJANGO_TARGET:?Django private hostport is required}"
: "${AMARIS_FLOWER_TARGET:?Flower private hostport is required}"
: "${RENDER_METRICS_TARGET:?Render metrics exporter hostport is required}"

sed -e "s|__DJANGO_TARGET__|${AMARIS_DJANGO_TARGET}|g" \
    -e "s|__FLOWER_TARGET__|${AMARIS_FLOWER_TARGET}|g" \
    -e "s|__RENDER_METRICS_TARGET__|${RENDER_METRICS_TARGET}|g" \
    /etc/prometheus/prometheus.yml.tmpl > /tmp/prometheus.yml

exec /bin/prometheus \
    --config.file=/tmp/prometheus.yml \
    --web.listen-address=0.0.0.0:${PORT:-10000} \
    --web.external-url="${MONITORING_PUBLIC_URL:-https://amaris-production-web.onrender.com/admin/monitoring/prometheus/}" \
    --web.route-prefix=/admin/monitoring/prometheus/ \
    --storage.tsdb.path=/prometheus-data \
    --storage.tsdb.retention.time=7d \
    --storage.tsdb.wal-compression

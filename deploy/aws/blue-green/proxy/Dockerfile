# syntax=docker/dockerfile:1
# Supply the exact reviewed ARM64 nginx digest, not a floating tag.
ARG NGINX_IMAGE
FROM ${NGINX_IMAGE}
COPY cms.conf /etc/nginx/conf.d/default.conf
COPY backend.inc /etc/nginx/conf.d/backend.inc
RUN nginx -t

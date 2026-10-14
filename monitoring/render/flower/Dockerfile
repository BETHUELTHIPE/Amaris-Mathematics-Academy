FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --no-cache-dir "celery==5.5.3" "flower==2.0.1" "redis>=5,<7"

EXPOSE 10000
CMD ["/bin/sh", "-ec", "test -n \"$CELERY_BROKER_URL\"; exec celery --broker=\"$CELERY_BROKER_URL\" flower --address=0.0.0.0 --port=\"${PORT:-10000}\" --url-prefix=admin/monitoring/flower --read-only=True"]

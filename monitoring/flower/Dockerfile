FROM python:3.13-slim
RUN pip install --no-cache-dir celery==5.5.3 flower==2.0.1
ENV PYTHONUNBUFFERED=1
EXPOSE 10000
CMD ["/bin/sh", "-ec", "test -n \"$CELERY_BROKER_URL\"; exec celery --broker=\"$CELERY_BROKER_URL\" flower --address=0.0.0.0 --port=\"${PORT:-10000}\""]

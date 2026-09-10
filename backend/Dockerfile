FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl libpq5 postgresql-client restic \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . ./
RUN groupadd --system amaris \
    && useradd --system --gid amaris --home-dir /app amaris \
    && mkdir -p /app/staticfiles /app/media \
    && chmod +x /app/entrypoint.sh /app/ops/*.sh \
    && chown -R amaris:amaris /app

USER amaris

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "amaris_cms.asgi:application", "--bind", "0.0.0.0:8000", "--worker-class", "uvicorn_worker.UvicornWorker", "--workers", "3", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]

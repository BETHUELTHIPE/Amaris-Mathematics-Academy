FROM python:3.13-slim

ARG RELEASE_SHA=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    RELEASE_SHA=${RELEASE_SHA}

LABEL org.opencontainers.image.revision="${RELEASE_SHA}"

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --no-install-recommends -y ca-certificates curl libpq5 postgresql-client restic \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt \
    && pip install --upgrade --force-reinstall "setuptools>=78.1.1" "msgpack>=1.2.1,<2.0" \
    && find /usr/local/lib/python3.13/site-packages -maxdepth 1 -type d \
         \( -name 'msgpack-1.1.2.dist-info' -o -name 'setuptools-70.3.0.dist-info' \) \
         -exec rm -rf {} + \
    && rm -rf /usr/local/lib/python3.13/site-packages/pip \
              /usr/local/lib/python3.13/site-packages/pip-*.dist-info \
    && rm -f /usr/local/bin/pip /usr/local/bin/pip3 /usr/local/bin/pip3.13

COPY . ./
RUN groupadd --system amaris \
    && useradd --system --gid amaris --home-dir /app amaris \
    && mkdir -p /app/staticfiles /app/media \
    && chmod +x /app/entrypoint.sh /app/ops/*.sh \
    && chown -R amaris:amaris /app

USER amaris

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "amaris_cms.asgi:application", "--config", "/app/gunicorn.conf.py"]

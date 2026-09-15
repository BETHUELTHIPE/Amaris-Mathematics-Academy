FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

ARG RESTIC_VERSION=0.19.1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl libpq5 postgresql-client \
    && arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
         amd64) restic_sha="f415415624dcc452f2a02b8c33641791a8c6d6d3b65bbb3543fcf9a25151585c" ;; \
         arm64) restic_sha="a5f64aaab53d51e311fa3829124c5b703f2d14cf187d8640b6be3b2b49376465" ;; \
         *) echo "Unsupported architecture for restic: $arch" >&2; exit 1 ;; \
       esac \
    && restic_asset="restic_${RESTIC_VERSION}_linux_${arch}.bz2" \
    && curl --fail --show-error --silent --location \
         --output "/tmp/${restic_asset}" \
         "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/${restic_asset}" \
    && echo "${restic_sha}  /tmp/${restic_asset}" | sha256sum --check --strict \
    && python -c "import bz2; open('/usr/local/bin/restic', 'wb').write(bz2.open('/tmp/${restic_asset}', 'rb').read())" \
    && chmod 0755 /usr/local/bin/restic \
    && restic version \
    && rm -f "/tmp/${restic_asset}" \
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
CMD ["gunicorn", "amaris_cms.asgi:application", "--config", "/app/gunicorn.conf.py"]

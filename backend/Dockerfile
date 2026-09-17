FROM golang:1.27.1-bookworm AS restic-builder

ARG RESTIC_VERSION=0.19.1
ARG RESTIC_SOURCE_SHA256=bb9b1a19040744d26d8a79be029d4e6b189c45ccc9d8831d7fe367d3c33df725

ENV CGO_ENABLED=0 \
    GOTOOLCHAIN=local

WORKDIR /build

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl \
    && curl --fail --show-error --silent --location \
         --output /tmp/restic.tar.gz \
         "https://github.com/restic/restic/releases/download/v${RESTIC_VERSION}/restic-${RESTIC_VERSION}.tar.gz" \
    && echo "${RESTIC_SOURCE_SHA256}  /tmp/restic.tar.gz" | sha256sum --check --strict \
    && tar -xzf /tmp/restic.tar.gz --strip-components=1 \
    && go get golang.org/x/crypto@v0.55.0 \
              golang.org/x/net@v0.58.0 \
              golang.org/x/text@v0.41.0 \
              google.golang.org/grpc@v1.83.2 \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/crypto)" = "v0.55.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/net)" = "v0.58.0" \
    && test "$(go list -m -f '{{.Version}}' golang.org/x/text)" = "v0.41.0" \
    && test "$(go list -m -f '{{.Version}}' google.golang.org/grpc)" = "v1.83.2" \
    && mkdir -p /out \
    && go build -trimpath -buildvcs=false -ldflags="-s -w" -o /out/restic ./cmd/restic \
    && /out/restic version \
    && go version -m /out/restic \
    && rm -f /tmp/restic.tar.gz \
    && rm -rf /var/lib/apt/lists/*

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --no-install-recommends -y ca-certificates libpq5 postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY --from=restic-builder /out/restic /usr/local/bin/restic
RUN chmod 0755 /usr/local/bin/restic \
    && restic version

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

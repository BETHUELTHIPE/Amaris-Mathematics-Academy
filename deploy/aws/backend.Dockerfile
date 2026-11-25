FROM docker.io/bethuelm/amaris-mathematics-academy@sha256:d8f1ecf5fd2ae97a8fec74bc4c0bc70be4407380986e8b9e3a4c12515f7fa68d

USER root
WORKDIR /app
RUN find /app -mindepth 1 -maxdepth 1 -exec rm -rf {} +
COPY --chown=amaris:amaris . .
RUN install -d -o amaris -g amaris /app/staticfiles /app/media \
    && chmod 755 /app/entrypoint.sh /app/ops/*.sh
USER amaris

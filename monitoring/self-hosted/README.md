# Private Prometheus and Grafana on an existing Docker host

This standalone stack adds no Render services and purchases no hosting. Prometheus and Grafana run on a server or computer the owner already controls. Hardware, electricity, storage and any existing hosting bills remain the owner's responsibility. Docker does not make Render private instances free: Render has no free private-service plan.

The two services use a private Docker bridge network, persistent named volumes, and ports bound only to `127.0.0.1`. The bridge permits outbound traffic for configured scrape targets; it does not publish dashboards publicly. Grafana requires a login; anonymous access and signup are disabled. A Compose secret file supplies the initial admin password. No production database, Celery queue, Flower service or Render service is changed by this stack.

## Start on the selected host

Use Docker Engine 28 or newer with Docker Compose. Earlier Engine versions have a known localhost port-publishing isolation issue. Choose an always-on host with spare CPU, RAM and disk; capacity must be measured against actual metrics volume. This directory is independent of `backend/docker-compose.yml`, so starting it does not start application workers or migrations.

From the repository root:

```sh
cd monitoring/self-hosted
umask 077
mkdir -p .secrets
# Generate once. Keep the existing file on subsequent deploys.
test -s .secrets/grafana_admin_password || openssl rand -hex 32 > .secrets/grafana_admin_password
chmod 700 .secrets
# Compose mounts this file into the unprivileged Grafana container.
chmod 444 .secrets/grafana_admin_password
docker compose config --quiet
docker compose up -d --wait
```

On a remote host, access both services through an SSH tunnel from your own computer:

```sh
ssh -N -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 USER@HOST
```

Open `http://localhost:3000` for Grafana and `http://localhost:9090` for Prometheus. Grafana's username is `amaris-admin`; retrieve its generated password securely on the host. Do not paste secrets into chat, GitHub, or deployment logs. For a Docker host on your own computer, no SSH tunnel is required. Do not publish these ports on `0.0.0.0` as a shortcut.

## Verification and production integration

Run `docker compose ps`, inspect `http://localhost:9090/-/ready`, and confirm the `prometheus` target is UP. In Grafana Explore, query `up{job="prometheus"}` using the provisioned Amaris Prometheus datasource. A value of 1 verifies only this collector, not the application's monitoring integration.

Initially Prometheus scrapes only itself. Render's internal hostnames are reachable only from its private network, so an external Docker host cannot scrape the existing Flower or Render exporter directly. Keep them private. Configure an authenticated private tunnel/VPN or an outbound metrics-forwarding path after the host is selected, then add the actual targets and credentials. Do not use invented hostnames or pretend empty application graphs are healthy. Verify that the Docker bridge can route to that private path.

The Django superuser proxy requires a backend-reachable private origin for Grafana and Prometheus. `localhost` on Render means the Render backend itself, not this Docker host. Leave the production origin variables unconfigured until that path and authentication are verified. This stack alone does not complete the authenticated Django admin verification or Celery worker verification.

## Data and operations

Prometheus retains seven days with a 1 GB block-retention limit; the WAL and head can require additional disk. Grafana uses its persistent local SQLite database for this single-instance installation. Back up both volumes and monitor host disk usage before relying on historical data. `docker compose down` preserves volumes; `docker compose down --volumes` deletes them. Changing the initial password file does not rotate an existing Grafana database password; use Grafana's supported password-reset procedure.

Keep the paid Render proposal in `../render/pending-services.yaml` unapplied while the owner requires no new hosting subscription. Deployment and real production integration remain pending selection of an accessible Docker host.

References: [Render free instance limitations](https://render.com/docs/free), [Docker port publishing](https://docs.docker.com/engine/network/port-publishing/), [Grafana Docker configuration](https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/).

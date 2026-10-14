# Amaris monitoring on Render

This profile keeps monitoring entirely on Render.

## Services

- Prometheus: private Docker service with a 1 GB persistent disk.
- Grafana: private Docker service with a 1 GB persistent disk.
- Flower: private Docker service connected to the existing `amaris-production-broker`.
- Render metrics exporter: private Docker service that converts Render's official CPU, memory, HTTP request, and HTTP latency API data into Prometheus metrics.

cAdvisor is intentionally absent. Render manages the host layer, so cAdvisor cannot truthfully measure Render's managed containers.

## Security

The monitoring services are private. The intended browser entrypoint is the Django Admin gateway at `/admin/monitoring/`, which is restricted to active Django superusers.

`RENDER_API_KEY` is a Render secret and must never be committed. The Blueprint leaves it as `sync: false`.

## Existing monitored resources

- Backend: `amaris-production-web` / `srv-dapn6b3tqb8s73d3r7n0`
- Student frontend: `amaris-mathematics-academy-live-students` / `srv-damn6d2d0e5s73d02j5g`
- Production broker: `amaris-production-broker` / `red-dapaglkja7ms73ajrkq0`
- Production cache: `amaris-production-cache` / `red-dapagn4ja7ms73ajrpi0`

## Deployment

Apply `monitoring/render/render.yaml` as a separate Blueprint after the code is merged to `main`. Do not replace the root production Blueprint.

Prometheus requires a paid service with a persistent disk; Render documents that free instances cannot provide the required durable storage. Grafana also uses a disk so its state survives deploys.

After Render creates the private services, configure the production backend with their private hostports:

- `MONITORING_CONSOLE_ENABLED=true`
- `MONITORING_GRAFANA_URL=http://<grafana-private-hostport>`
- `MONITORING_PROMETHEUS_URL=http://<prometheus-private-hostport>`
- `MONITORING_FLOWER_URL=http://<flower-private-hostport>`

The backend must remain in Frankfurt so it can reach the monitoring services through Render's private network.

## Verification

Confirm:

1. all four monitoring services are live;
2. Prometheus targets `prometheus`, `django`, `flower`, and `render-native` are up;
3. `render_metrics_exporter_refresh_success == 1`;
4. Grafana panels show real Render metrics and N/A where data is unavailable;
5. a non-superuser receives 403/permission denied for the Django monitoring gateway;
6. the public internet cannot directly reach the private Prometheus, Grafana, Flower, or exporter services.

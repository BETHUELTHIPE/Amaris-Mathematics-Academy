from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

MONITORING_TOOLS = (
    ("flower", "Flower", "Celery workers, scheduled tasks and task activity.", "fas fa-seedling"),
    ("prometheus", "Prometheus", "Metrics queries, scrape targets and alert rules.", "fas fa-fire"),
    ("grafana", "Grafana", "Platform dashboards, trends and alerts.", "fas fa-chart-line"),
    ("cadvisor", "cAdvisor", "Container CPU, memory, network and filesystem usage.", "fas fa-server"),
    ("alertmanager", "Alertmanager", "Active alerts, alert groups and silences.", "fas fa-bell"),
)

MONITORING_DASHBOARDS = (
    ("PostgreSQL", "Database availability and connection activity.", "fas fa-database", "amaris-postgresql"),
    ("Redis broker", "Celery broker availability, memory and clients.", "fas fa-tasks", "amaris-redis-broker"),
    ("Redis cache", "Cache availability, memory and clients.", "fas fa-bolt", "amaris-redis-cache"),
    ("Docker host", "Server CPU, memory and filesystem capacity.", "fas fa-server", "amaris-host"),
    ("Website uptime", "Website and backend availability and probe duration.", "fas fa-globe", "amaris-uptime"),
)


def validate_monitoring_url(value):
    """Allow browser URLs without embedding infrastructure credentials."""
    value = value.strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError as error:
        raise ImproperlyConfigured("Invalid admin monitoring URL.") from error
    relative = value.startswith("/") and not value.startswith("//") and not parts.netloc
    absolute = parts.scheme in {"http", "https"} and bool(parts.hostname)
    if (
        not (relative or absolute)
        or parts.username is not None
        or parts.password is not None
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        raise ImproperlyConfigured(
            "Admin monitoring URLs must be HTTP(S) URLs or root-relative paths without credentials."
        )
    return value


def monitoring_urls(base_url, proxy_enabled, overrides):
    base = validate_monitoring_url(base_url)
    if urlsplit(base).query or urlsplit(base).fragment:
        raise ImproperlyConfigured("The monitoring base URL must not contain a query or fragment.")
    prefix = base.rstrip("/")
    return {
        key: validate_monitoring_url(
            overrides.get(key, "").strip() or (f"{prefix}/monitoring/{key}/" if base or proxy_enabled else "")
        )
        for key, *_ in MONITORING_TOOLS
    }

from uvicorn_worker import UvicornWorker


class PrivacyUvicornWorker(UvicornWorker):
    """ASGI worker with Uvicorn client-address access logging disabled.

    Request health and latency remain observable through django-prometheus and
    correlation-aware application errors without recording client IP addresses,
    referrers, user agents, query strings, or student identifiers.
    """

    CONFIG_KWARGS = {
        **UvicornWorker.CONFIG_KWARGS,
        "access_log": False,
    }

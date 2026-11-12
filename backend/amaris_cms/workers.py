import os

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

    def __init__(self, *args, **kwargs):
        concurrency = int(os.getenv("UVICORN_LIMIT_CONCURRENCY", "32"))
        if concurrency < 2:
            raise ValueError("UVICORN_LIMIT_CONCURRENCY must be at least 2.")
        # Gunicorn's worker_connections does not apply to Uvicorn workers.
        # Configure admission control on the actual ASGI server instead.
        self.CONFIG_KWARGS = {
            **type(self).CONFIG_KWARGS,
            "limit_concurrency": concurrency,
            "timeout_graceful_shutdown": int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30")),
        }
        super().__init__(*args, **kwargs)

import os

from amaris_cms.runtime_config import recommended_workers


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
worker_class = "amaris_cms.workers.PrivacyUvicornWorker"
workers = env_int("WEB_CONCURRENCY", recommended_workers())
timeout = env_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)
worker_tmp_dir = "/dev/shm"
# Bound the socket queue as well as each ASGI worker's active requests.
backlog = env_int("GUNICORN_BACKLOG", 256)
# Never share database pools or the notification supervisor across a fork.
preload_app = False
accesslog = "-"
# Privacy-preserving access log: omit client IP, query strings, referrer and user-agent.
access_log_format = '%(t)s "%(m)s %(U)s" %(s)s %(b)s %(L)s'
errorlog = "-"
capture_output = True


def when_ready(server):
    # Opt-in only: never start a second scheduler in Gunicorn request workers.
    # Production Render has one web instance; no new service is provisioned.
    from amaris_cms.colocated_notifications import start_notifications

    start_notifications(server.log)


def on_exit(server):
    from amaris_cms.colocated_notifications import stop_notifications

    stop_notifications(server.log)

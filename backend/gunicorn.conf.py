import os


def env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")
worker_class = "uvicorn_worker.UvicornWorker"
workers = env_int("WEB_CONCURRENCY", 3)
timeout = env_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = env_int("GUNICORN_KEEPALIVE", 5)
max_requests = env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)
worker_tmp_dir = "/dev/shm"
accesslog = "-"
errorlog = "-"
capture_output = True

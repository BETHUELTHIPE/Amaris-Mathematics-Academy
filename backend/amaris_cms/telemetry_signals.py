"""Create the SDK/export thread inside Celery children, never before prefork."""

from celery.signals import beat_init, worker_init, worker_process_init, worker_process_shutdown, worker_shutdown

from .telemetry import flush_traces, initialize_tracing


@worker_process_init.connect(weak=False)
def initialize_worker_tracing(**_kwargs):
    initialize_tracing("celery")


@worker_init.connect(weak=False)
def initialize_nonfork_worker_tracing(sender=None, **_kwargs):
    pool = getattr(sender, "pool_cls", None)
    if getattr(pool, "__module__", "") in {"celery.concurrency.solo", "celery.concurrency.thread"}:
        initialize_tracing("celery")


@beat_init.connect(weak=False)
def initialize_beat_tracing(**_kwargs):
    initialize_tracing("beat")


@worker_process_shutdown.connect(weak=False)
@worker_shutdown.connect(weak=False)
def flush_worker_traces(**_kwargs):
    flush_traces()

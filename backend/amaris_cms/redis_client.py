"""Bounded process-wide Redis pools for Django's request-local cache clients."""

import os
import threading
from collections.abc import Callable
from typing import Any

from django.core.cache.backends.redis import RedisCacheClient
from redis import ConnectionPool
from redis.exceptions import ConnectionError as RedisConnectionError


class ProcessRedisCacheClient(RedisCacheClient):
    # Django 5.2 initializes these in its RedisCacheClient, but its type stubs
    # do not describe the protected connection-pool interface.
    _servers: list[str]
    _pool_class: type[ConnectionPool]
    _pool_options: dict[str, Any]
    _get_connection_pool_index: Callable[[bool], int]
    _shared_pools: dict[tuple, ConnectionPool] = {}
    _pool_lock = threading.RLock()
    _pool_pid = os.getpid()
    _max_pools = 32

    def __init__(self, servers, **options):
        options.setdefault("max_connections", 30)
        if int(options["max_connections"]) <= 0:
            raise ValueError("Redis cache max_connections must be positive.")
        super().__init__(servers, **options)

    def _get_connection_pool(self, write):
        cls = type(self)
        # Check before taking the lock: a prefork child must not inherit a lock
        # held by another parent thread, or use the parent's socket registry.
        if cls._pool_pid != os.getpid():
            cls._shared_pools = {}
            cls._pool_lock = threading.RLock()
            cls._pool_pid = os.getpid()
        index = self._get_connection_pool_index(write)
        key = (
            self._servers[index],
            self._pool_class,
            tuple(sorted((name, repr(value)) for name, value in self._pool_options.items())),
        )
        with cls._pool_lock:
            if key not in cls._shared_pools:
                if len(cls._shared_pools) >= cls._max_pools:
                    raise RedisConnectionError("Redis cache pool registry limit reached.")
                cls._shared_pools[key] = self._pool_class.from_url(self._servers[index], **self._pool_options)
            return cls._shared_pools[key]

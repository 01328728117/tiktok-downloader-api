"""Cache + task result storage abstraction with Redis or in-memory fallback."""

from __future__ import annotations

import json
import time
from threading import RLock
from typing import Any

import redis

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class _MemoryStore:
    """Thread-safe in-process key-value store with TTL support."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float | None, str]] = {}
        self._lock = RLock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if expires_at is not None and expires_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        with self._lock:
            expires_at = time.time() + ex if ex else None
            self._data[key] = (expires_at, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def ping(self) -> bool:
        return True


class CacheBackend:
    """High-level cache + task storage façade backed by Redis or memory."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._prefix = self._settings.cache_prefix
        self._memory = _MemoryStore()
        self._redis: redis.Redis | None = None

        if self._settings.has_redis:
            try:
                self._redis = redis.Redis.from_url(
                    self._settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                self._redis.ping()
                logger.info("cache_redis_connected", url=self._settings.redis_url)
            except (redis.RedisError, OSError) as exc:
                logger.warning("cache_redis_unavailable", error=str(exc))
                self._redis = None

    # ----- generic key/value -----

    def _key(self, key: str) -> str:
        return f"{self._prefix}{key}" if not key.startswith(self._prefix) else key

    def get_json(self, key: str) -> Any | None:
        raw = self._raw_get(self._key(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            return None

    def set_json(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = ttl if ttl is not None else self._settings.cache_ttl_seconds
        self._raw_set(self._key(key), json.dumps(value), ttl)

    def delete(self, key: str) -> None:
        self._raw_delete(self._key(key))

    def _raw_get(self, key: str) -> str | None:
        if self._redis is not None:
            try:
                return self._redis.get(key)
            except redis.RedisError as exc:
                logger.warning("cache_get_failed", error=str(exc))
        return self._memory.get(key)

    def _raw_set(self, key: str, value: str, ttl: int | None) -> None:
        if self._redis is not None:
            try:
                if ttl:
                    self._redis.set(key, value, ex=ttl)
                else:
                    self._redis.set(key, value)
                return
            except redis.RedisError as exc:
                logger.warning("cache_set_failed", error=str(exc))
        self._memory.set(key, value, ex=ttl)

    def _raw_delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
                return
            except redis.RedisError as exc:
                logger.warning("cache_delete_failed", error=str(exc))
        self._memory.delete(key)

    # ----- task results -----

    def task_key(self, task_id: str) -> str:
        return f"task:{task_id}"

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self.get_json(self.task_key(task_id))

    def set_task(self, task_id: str, data: dict[str, Any], ttl: int | None = None) -> None:
        self.set_json(self.task_key(task_id), data, ttl=ttl)

    # ----- diagnostics -----

    def ping(self) -> dict[str, Any]:
        if self._redis is None:
            return {"backend": "memory", "ok": True}
        try:
            ok = bool(self._redis.ping())
            return {"backend": "redis", "ok": ok}
        except redis.RedisError as exc:
            return {"backend": "redis", "ok": False, "error": str(exc)}

    @property
    def backend(self) -> str:
        return "redis" if self._redis is not None else "memory"

    def clear(self) -> None:
        """Test helper — clear all cache state."""
        self._memory.clear()
        if self._redis is not None:
            try:
                for key in self._redis.scan_iter(f"{self._prefix}*"):
                    self._redis.delete(key)
            except redis.RedisError:
                pass


_cache_instance: CacheBackend | None = None


def get_cache() -> CacheBackend:
    """Return a process-wide CacheBackend singleton."""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheBackend()
    return _cache_instance


def reset_cache_singleton() -> None:
    """Drop the singleton (used in tests)."""
    global _cache_instance
    _cache_instance = None

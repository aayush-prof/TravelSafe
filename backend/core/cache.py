"""
Small thread-safe TTL cache with explicit freshness metadata.

* Successful results are cached for ``ttl``.
* Failed/degraded results are cached only briefly (``failure_ttl``) so a
  transient outage does not stick, but the frontend's parallel requests do
  not hammer providers either.
* An expired *successful* entry can still be served as **stale** if a
  refresh fails (``get_stale``), and it is labelled as such.
* A per-key lock prevents duplicate concurrent fetches for the same city.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple


@dataclass
class CacheEntry:
    value: Any
    stored_at: float
    expires_at: float
    ok: bool

    @property
    def age_seconds(self) -> float:
        return time.time() - self.stored_at


class TTLCache:
    def __init__(self) -> None:
        self._data: Dict[str, CacheEntry] = {}
        self._good: Dict[str, CacheEntry] = {}  # last successful entry per key
        self._lock = threading.Lock()
        self._key_locks: Dict[str, threading.Lock] = {}
        self.hits = 0
        self.misses = 0

    def _key_lock(self, key: str) -> threading.Lock:
        with self._lock:
            return self._key_locks.setdefault(key, threading.Lock())

    def get_fresh(self, key: str) -> Optional[CacheEntry]:
        with self._lock:
            entry = self._data.get(key)
        if entry and time.time() < entry.expires_at:
            self.hits += 1
            return entry
        return None

    def get_stale(self, key: str, max_age: float) -> Optional[CacheEntry]:
        with self._lock:
            entry = self._good.get(key)
        if entry and entry.age_seconds <= max_age:
            return entry
        return None

    def set(self, key: str, value: Any, ttl: float, ok: bool) -> CacheEntry:
        now = time.time()
        entry = CacheEntry(value, now, now + max(0.0, ttl), ok)
        with self._lock:
            self._data[key] = entry
            if ok:
                self._good[key] = entry
        return entry

    def get_or_compute(self, key: str, compute: Callable[[], Tuple[Any, bool]], ttl: float,
                       failure_ttl: float) -> Tuple[CacheEntry, bool]:
        """Return (entry, from_cache). ``compute`` returns (value, ok)."""
        entry = self.get_fresh(key)
        if entry:
            return entry, True
        with self._key_lock(key):
            entry = self.get_fresh(key)
            if entry:
                return entry, True
            self.misses += 1
            value, ok = compute()
            entry = self.set(key, value, ttl if ok else failure_ttl, ok)
            return entry, False

    def invalidate(self, predicate: Callable[[str], bool]) -> int:
        """Drop fresh entries whose key matches. Last-good copies are kept for
        stale fallback, so a refresh that fails can still show older data."""
        with self._lock:
            keys = [k for k in self._data if predicate(k)]
            for k in keys:
                del self._data[k]
        return len(keys)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self._good.clear()

    def stats(self) -> Dict[str, int]:
        return {"entries": len(self._data), "hits": self.hits, "misses": self.misses}


cache = TTLCache()

"""Short-lived, in-memory conversation state (no message text is kept)."""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass
class Session:
    state: str = "idle"
    data: dict = field(default_factory=dict)
    updated: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, ttl_seconds: int = 1800):
        self.ttl = ttl_seconds
        self._items: dict[str, Session] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Session:
        now = time.time()
        with self._lock:
            self._purge(now)
            sess = self._items.get(key)
            if sess is None:
                sess = self._items[key] = Session()
            sess.updated = now
            return sess

    def delete(self, key: str) -> bool:
        with self._lock:
            return self._items.pop(key, None) is not None

    def __len__(self) -> int:
        return len(self._items)

    def _purge(self, now: float) -> None:
        expired = [k for k, s in self._items.items() if now - s.updated > self.ttl]
        for k in expired:
            del self._items[k]

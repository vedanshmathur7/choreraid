"""Small thread-safe LRU cache for cleanup plans (avoids repeat Gemini calls)."""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from collections.abc import Iterable
from typing import Generic, TypeVar

from .models import FileMeta

T = TypeVar("T")


class PlanCache(Generic[T]):
    """Least-recently-used cache with a fixed size. O(1) get/put."""

    def __init__(self, max_entries: int = 128) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be >= 1")
        self._max = max_entries
        self._data: OrderedDict[str, T] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def key_for(files: Iterable[FileMeta]) -> str:
        """Order-independent fingerprint of a folder listing."""
        digest = hashlib.sha256()
        for name in sorted(f"{f.name}\x00{f.size}" for f in files):
            digest.update(name.encode("utf-8", "replace"))
            digest.update(b"\x01")
        return digest.hexdigest()

    def get(self, key: str) -> T | None:
        with self._lock:
            if key not in self._data:
                return None
            self._data.move_to_end(key)
            return self._data[key]

    def put(self, key: str, value: T) -> None:
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self._max:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)

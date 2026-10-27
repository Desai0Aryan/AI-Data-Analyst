"""Tiny in-memory TTL cache for answers.

The dataset is static and the LLM is the expensive part, so an identical question (same model,
same reference date) can reuse its answer. Only finished, successful outcomes are cached
(ok / cannot_answer): a failure should be retried, not remembered.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any

from .llm.replay import normalize_question


def cache_key(question: str, model: str, reference_date: str) -> str:
    return f"{model}|{reference_date}|{normalize_question(question)}"


class TTLCache:
    def __init__(self) -> None:
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None or item[0] < time.monotonic():
                self._data.pop(key, None)
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return item[1]

    def set(self, key: str, value: Any, ttl_s: int, max_entries: int) -> None:
        if ttl_s <= 0:
            return
        with self._lock:
            self._data[key] = (time.monotonic() + ttl_s, value)
            self._data.move_to_end(key)
            while len(self._data) > max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
            self.hits = self.misses = 0

    def __len__(self) -> int:
        return len(self._data)


answers = TTLCache()

"""KRONOS Event Bus — thread-safe pub/sub message passing between modules."""
import threading
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List


class Event:
    __slots__ = ("topic", "data", "source", "ts")

    def __init__(self, topic: str, data: Any, source: str):
        self.topic = topic
        self.data = data
        self.source = source
        self.ts = time.time()


class KronosEventBus:
    """Central message router. Modules publish topics; other modules subscribe.

    Handlers are called synchronously in the publisher's thread — keep them fast
    or dispatch to a queue if heavy work is needed.
    """

    MAX_HISTORY = 500

    def __init__(self):
        self._lock = threading.Lock()
        self._subs: Dict[str, List[Callable]] = defaultdict(list)
        self._history: List[Event] = []
        self._total = 0

    def subscribe(self, topic: str, handler: Callable) -> None:
        with self._lock:
            self._subs[topic].append(handler)

    def publish(self, topic: str, data: Any = None, source: str = "") -> None:
        event = Event(topic, data, source)
        with self._lock:
            handlers = list(self._subs.get(topic, []))
            self._history.append(event)
            if len(self._history) > self.MAX_HISTORY:
                del self._history[0]
            self._total += 1
        for h in handlers:
            try:
                h(event)
            except Exception:
                pass  # handlers must never crash the bus

    def recent(self, n: int = 30) -> List[dict]:
        with self._lock:
            return [
                {"topic": e.topic, "source": e.source, "ts": round(e.ts, 2)}
                for e in self._history[-n:]
            ]

    @property
    def total_events(self) -> int:
        return self._total

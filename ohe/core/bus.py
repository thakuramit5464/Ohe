"""
core/bus.py
-----------
In-process publish/subscribe DataBus.

Subscribers register a callable per topic. Publishers call ``publish()``
and all registered subscribers receive the payload synchronously (or the
message is queued for async consumption — see QueuedSubscriber).

Design notes
------------
* Topics are plain strings e.g. "measurement", "anomaly", "frame".
* For UI integration (Phase 4) a QueuedSubscriber wraps the queue so the
  worker thread can push data and the Qt main thread can poll via a timer.
* Thread-safety: subscription registration should happen before threads
  start; ``publish`` itself is thread-safe for queue-based subscribers.
"""

from __future__ import annotations

import logging
import queue
import threading
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

Topic = str
Handler = Callable[[Any], None]


class DataBus:
    """Lightweight synchronous publish/subscribe bus."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: dict[Topic, list[Handler]] = defaultdict(list)

    def subscribe(self, topic: Topic, handler: Handler) -> None:
        """Register *handler* to be called whenever *topic* is published."""
        with self._lock:
            self._handlers[topic].append(handler)
        logger.debug("DataBus: subscribed %s to topic '%s'", handler, topic)

    def unsubscribe(self, topic: Topic, handler: Handler) -> None:
        """Remove *handler* from *topic*. No-op if not registered."""
        with self._lock:
            handlers = self._handlers.get(topic, [])
            try:
                handlers.remove(handler)
            except ValueError:
                pass

    def publish(self, topic: Topic, payload: Any) -> None:
        """Deliver *payload* to all subscribers of *topic*.

        Exceptions raised by individual handlers are logged but do not stop
        delivery to the remaining subscribers.
        """
        with self._lock:
            handlers = list(self._handlers.get(topic, []))

        for handler in handlers:
            try:
                handler(payload)
            except Exception:
                logger.exception(
                    "DataBus: handler %s raised an error on topic '%s'", handler, topic
                )

    def topics(self) -> list[Topic]:
        """Return the list of topics that have at least one subscriber."""
        with self._lock:
            return [t for t, h in self._handlers.items() if h]


class QueuedSubscriber:
    """Thread-safe bridge: puts published payloads into a queue.Queue.

    Useful for handing data from a worker thread to the Qt UI thread.

    Example::

        qs = QueuedSubscriber()
        bus.subscribe("measurement", qs.put)
        # In Qt timer callback:
        while not qs.empty():
            m = qs.get()
            update_chart(m)
    """

    def __init__(self, maxsize: int = 0) -> None:
        self._q: queue.Queue[Any] = queue.Queue(maxsize=maxsize)

    # Allow this object to be passed directly as a handler
    def __call__(self, payload: Any) -> None:
        self.put(payload)

    def put(self, payload: Any) -> None:
        try:
            self._q.put_nowait(payload)
        except queue.Full:
            logger.warning("QueuedSubscriber: queue full, dropping payload %s", type(payload))

    def get(self, block: bool = False) -> Any:
        return self._q.get(block=block)

    def empty(self) -> bool:
        return self._q.empty()

    def drain(self) -> list[Any]:
        """Return all currently queued items without blocking."""
        items: list[Any] = []
        while not self._q.empty():
            try:
                items.append(self._q.get_nowait())
            except queue.Empty:
                break
        return items


# Module-level default shared bus instance
_default_bus: DataBus | None = None
_bus_lock = threading.Lock()


def get_default_bus() -> DataBus:
    """Return (and lazily create) the module-level singleton DataBus."""
    global _default_bus
    with _bus_lock:
        if _default_bus is None:
            _default_bus = DataBus()
    return _default_bus

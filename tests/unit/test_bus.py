"""tests/unit/test_bus.py — DataBus pub/sub tests."""

import threading
import pytest

from ohe.core.bus import DataBus, QueuedSubscriber


class TestDataBus:
    def test_subscribe_and_receive(self):
        bus = DataBus()
        received = []
        bus.subscribe("test", received.append)
        bus.publish("test", 42)
        assert received == [42]

    def test_multiple_subscribers(self):
        bus = DataBus()
        a, b = [], []
        bus.subscribe("x", a.append)
        bus.subscribe("x", b.append)
        bus.publish("x", "hello")
        assert a == ["hello"]
        assert b == ["hello"]

    def test_unsubscribe(self):
        bus = DataBus()
        received = []
        bus.subscribe("t", received.append)
        bus.unsubscribe("t", received.append)
        bus.publish("t", 1)
        assert received == []

    def test_publish_to_unknown_topic_is_noop(self):
        bus = DataBus()
        bus.publish("nonexistent", "data")  # should not raise

    def test_handler_exception_doesnt_stop_other_handlers(self):
        bus = DataBus()
        results = []

        def bad_handler(payload):
            raise ValueError("intentional")

        bus.subscribe("t", bad_handler)
        bus.subscribe("t", results.append)
        bus.publish("t", "payload")
        assert results == ["payload"]

    def test_thread_safe_concurrent_publish(self):
        bus = DataBus()
        results = []
        lock = threading.Lock()

        def handler(p):
            with lock:
                results.append(p)

        bus.subscribe("t", handler)
        threads = [threading.Thread(target=bus.publish, args=("t", i)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 50

    def test_topics_returns_subscribed_topics(self):
        bus = DataBus()
        bus.subscribe("alpha", lambda x: x)
        assert "alpha" in bus.topics()


class TestQueuedSubscriber:
    def test_put_and_drain(self):
        qs = QueuedSubscriber()
        qs(1)
        qs(2)
        items = qs.drain()
        assert items == [1, 2]

    def test_empty_after_drain(self):
        qs = QueuedSubscriber()
        qs("a")
        qs.drain()
        assert qs.empty()

    def test_maxsize_drops_on_full(self):
        qs = QueuedSubscriber(maxsize=2)
        qs(1)
        qs(2)
        qs(3)  # should be dropped silently
        assert qs.drain() == [1, 2]

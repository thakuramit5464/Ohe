"""tests/unit/test_log_worker.py — LogWorker background thread tests."""

from __future__ import annotations

import time
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ohe.core.models import Anomaly, Measurement
from ohe.logging_.log_worker import LogWorker


def make_measurement(frame_id=0) -> Measurement:
    return Measurement(
        frame_id=frame_id,
        timestamp_ms=frame_id * 33.3,
        stagger_mm=10.0,
        diameter_mm=12.0,
        confidence=0.8,
    )


def make_anomaly(frame_id=0) -> Anomaly:
    return Anomaly(
        frame_id=frame_id, timestamp_ms=0.0,
        anomaly_type="STAGGER_RIGHT", value=160.0, threshold=150.0,
        severity="WARNING", message="test",
    )


class TestLogWorker:
    def test_push_and_write_to_session(self):
        """All pushed items must be written to the session logger."""
        session = MagicMock()
        worker = LogWorker(session, csv_writer=None, maxsize=100)
        worker.start()

        for i in range(5):
            worker.push_measurement(make_measurement(i))

        worker.stop()

        assert session.log_measurement.call_count == 5

    def test_anomalies_written(self):
        session = MagicMock()
        worker = LogWorker(session, csv_writer=None)
        worker.start()

        a = make_anomaly()
        worker.push_measurement(make_measurement(), anomalies=[a])
        worker.stop()

        session.log_anomaly.assert_called_once()

    def test_csv_writer_called(self):
        session = MagicMock()
        csv = MagicMock()
        worker = LogWorker(session, csv_writer=csv)
        worker.start()

        worker.push_measurement(make_measurement())
        worker.stop()

        csv.write.assert_called_once()

    def test_queue_full_drops_gracefully(self):
        """When the queue is full, push_measurement must not raise."""
        session = MagicMock()
        # maxsize=1 and deliberately do NOT start the worker so it never drains
        worker = LogWorker(session, csv_writer=None, maxsize=1)

        # First push fills the queue (worker not started, nothing drains)
        worker.push_measurement(make_measurement(0))
        # Second push should be silently dropped, not raise
        worker.push_measurement(make_measurement(1))
        assert worker.dropped_count >= 1

    def test_stop_is_idempotent(self):
        """stop() on an unstarted worker must not raise."""
        session = MagicMock()
        worker = LogWorker(session, csv_writer=None)
        worker.stop()   # never started — should not raise

    def test_start_stop_lifecycle(self):
        session = MagicMock()
        worker = LogWorker(session, csv_writer=None)
        worker.start()
        assert worker._thread is not None
        assert worker._thread.is_alive()
        worker.stop()
        time.sleep(0.05)
        assert not worker._thread.is_alive()

    def test_high_volume_no_drops(self):
        """100 items with maxsize=200 should result in zero drops."""
        session = MagicMock()
        worker = LogWorker(session, csv_writer=None, maxsize=200)
        worker.start()

        for i in range(100):
            worker.push_measurement(make_measurement(i))

        worker.stop()

        assert worker.dropped_count == 0
        assert session.log_measurement.call_count == 100

"""
logging_/log_worker.py
-----------------------
Background-thread log worker.

Decouples the hot processing pipeline from the (relatively slow) SQLite and
CSV I/O using a thread-safe queue.  The pipeline simply calls push() and
returns immediately; the worker thread drains the queue at its own pace.

Usage::

    from ohe.logging_.log_worker import LogWorker
    from ohe.logging_.session import SessionLogger
    from ohe.logging_.csv_writer import CsvWriter

    session = SessionLogger(session_dir, source=video_path)
    info    = session.start()
    csv     = CsvWriter(session_dir, info.session_id)
    worker  = LogWorker(session, csv)

    worker.start()
    # ... pipeline loop ...
    worker.push_measurement(measurement, anomalies)
    # ...
    worker.stop()          # blocks until queue drains
    session.stop()
"""

from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

from ohe.core.models import Anomaly, Measurement
from ohe.logging_.csv_writer import CsvWriter
from ohe.logging_.session import SessionLogger

logger = logging.getLogger(__name__)

# Sentinel to signal the worker to exit
_STOP = object()


class LogWorker:
    """Thread-safe, non-blocking measurement / anomaly logger.

    The worker owns a ``queue.Queue`` that accepts ``(Measurement, [Anomaly])``
    tuples.  A daemon background thread consumes items and writes them to
    both the :class:`SessionLogger` (SQLite) and :class:`CsvWriter`.
    """

    def __init__(
        self,
        session: SessionLogger,
        csv_writer: Optional[CsvWriter] = None,
        maxsize: int = 500,
    ) -> None:
        self._session = session
        self._csv = csv_writer
        self._q: queue.Queue = queue.Queue(maxsize=maxsize)
        self._thread: Optional[threading.Thread] = None
        self._dropped = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the background writer thread."""
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="LogWorker", daemon=True)
        self._thread.start()
        logger.debug("LogWorker started")

    def stop(self, timeout: float = 10.0) -> None:
        """Signal stop and wait for the queue to drain (up to *timeout* seconds)."""
        try:
            self._q.put_nowait(_STOP)
        except queue.Full:
            logger.warning("LogWorker: queue full on stop — forcing shutdown")
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("LogWorker: thread did not exit within %.1fs", timeout)
        if self._dropped:
            logger.warning("LogWorker: %d item(s) were dropped due to full queue", self._dropped)

    # ------------------------------------------------------------------
    # Public push API (called from pipeline thread)
    # ------------------------------------------------------------------

    def push_measurement(self, m: Measurement, anomalies: list[Anomaly] | None = None) -> None:
        """Enqueue a measurement+anomaly pair for async writing.

        If the queue is full the item is silently dropped (with a counter).
        """
        try:
            self._q.put_nowait((m, anomalies or []))
        except queue.Full:
            self._dropped += 1
            if self._dropped % 100 == 0:
                logger.warning("LogWorker: queue full — %d items dropped so far", self._dropped)

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop for the background writer thread."""
        while True:
            try:
                item = self._q.get(timeout=1.0)
            except queue.Empty:
                continue

            if item is _STOP:
                # Drain remaining items before exiting
                self._drain_remaining()
                break

            m, anomalies = item
            self._write(m, anomalies)
            self._q.task_done()

        logger.debug("LogWorker thread exiting")

    def _drain_remaining(self) -> None:
        """Empty the queue after receiving the stop sentinel."""
        while True:
            try:
                item = self._q.get_nowait()
                if item is _STOP:
                    continue
                m, anomalies = item
                self._write(m, anomalies)
                self._q.task_done()
            except queue.Empty:
                break

    def _write(self, m: Measurement, anomalies: list[Anomaly]) -> None:
        """Write measurement + anomalies to both sinks."""
        try:
            self._session.log_measurement(m)
            for a in anomalies:
                self._session.log_anomaly(a)
        except Exception:
            logger.exception("LogWorker: SQLite write failed for frame %d", m.frame_id)

        if self._csv:
            try:
                self._csv.write(m, anomalies)
            except Exception:
                logger.exception("LogWorker: CSV write failed for frame %d", m.frame_id)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def queue_size(self) -> int:
        return self._q.qsize()

    @property
    def dropped_count(self) -> int:
        return self._dropped

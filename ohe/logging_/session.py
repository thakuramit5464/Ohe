"""
logging_/session.py
--------------------
Session lifecycle manager + SQLite writer.

Creates one SQLite database per session in ``config.logging.session_dir``
and writes measurements and anomalies as they arrive.

Schema
------
sessions       (session_id, source, started_at_ms, ended_at_ms, total_frames, anomaly_count, notes)
measurements   (session_id, frame_id, timestamp_ms, stagger_mm, diameter_mm, confidence, wire_bbox)
anomalies      (session_id, frame_id, timestamp_ms, anomaly_type, value, threshold, severity, message)

Thread safety
-------------
All public write methods acquire ``_lock`` before touching the connection.
This allows the LogWorker background thread and the pipeline thread to both
call methods on the same SessionLogger without triggering "cannot commit –
no transaction is active" races.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Optional

from ohe.core.models import Anomaly, Measurement, SessionInfo

logger = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    source       TEXT,
    started_at_ms REAL,
    ended_at_ms  REAL,
    total_frames INTEGER DEFAULT 0,
    anomaly_count INTEGER DEFAULT 0,
    event_clip_count INTEGER DEFAULT 0,
    track_name   TEXT DEFAULT '',
    notes        TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS measurements (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT,
    frame_id     INTEGER,
    timestamp_ms REAL,
    stagger_mm   REAL,
    diameter_mm  REAL,
    confidence   REAL,
    wire_bbox    TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS anomalies (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT,
    frame_id       INTEGER,
    timestamp_ms   REAL,
    anomaly_type   TEXT,
    value          REAL,
    threshold      REAL,
    severity       TEXT,
    message        TEXT,
    latitude       REAL,
    longitude      REAL,
    speed_kmh      REAL,
    video_clip     TEXT,
    model_version  TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


def _safe_commit(conn: sqlite3.Connection) -> None:
    """Commit only when there is an active transaction; silently skip otherwise.

    sqlite3 in Python operates in *deferred transaction* mode by default —
    ``conn.in_transaction`` is True whenever DML has been issued since the
    last commit/rollback.  Calling commit() when ``in_transaction`` is False
    is a no-op in SQLite, but we guard explicitly to be safe across versions.
    """
    try:
        if conn.in_transaction:
            conn.commit()
    except sqlite3.OperationalError as exc:
        # "cannot commit – no transaction is active" → already committed/rolled back
        logger.debug("_safe_commit: suppressed OperationalError — %s", exc)
    except Exception:
        logger.exception("_safe_commit: unexpected error")


class SessionLogger:
    """Manages a single measurement session: SQLite writer + session metadata.

    All public methods are thread-safe: a ``threading.Lock`` serialises every
    operation that touches the SQLite connection.
    """

    def __init__(
        self,
        session_dir: Path,
        source: str,
        notes: str = "",
        track_name: str = "",
    ) -> None:
        self._session_dir = session_dir
        self._source = source
        self._notes = notes
        self._track_name = track_name
        self._session_id: str = ""
        self._db_path: Optional[Path] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._info: Optional[SessionInfo] = None
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> SessionInfo:
        """Open a new session and create the SQLite database."""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%S")
        self._session_id = f"{ts}_{uuid.uuid4().hex[:6]}"
        self._db_path = self._session_dir / f"{self._session_id}.sqlite"

        conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
        # WAL mode: allows concurrent readers + one writer, much safer
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.executescript(_DDL)
        _safe_commit(conn)
        self._conn = conn

        started_at = time.time() * 1000
        with self._lock:
            self._conn.execute(
                "INSERT INTO sessions (session_id, source, started_at_ms, track_name, notes) "
                "VALUES (?,?,?,?,?)",
                (self._session_id, self._source, started_at,
                 self._track_name, self._notes),
            )
            _safe_commit(self._conn)

        self._info = SessionInfo(
            session_id=self._session_id,
            source=self._source,
            started_at_ms=started_at,
            track_name=self._track_name,
            notes=self._notes,
        )
        logger.info("Session started: %s → %s", self._session_id, self._db_path)
        return self._info

    def stop(self) -> SessionInfo:
        """Close the session and finalise the database record."""
        if self._conn is None or self._info is None:
            raise RuntimeError("Session not started.")
        ended_at = time.time() * 1000
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE sessions SET ended_at_ms=?, total_frames=?, "
                    "anomaly_count=?, event_clip_count=? WHERE session_id=?",
                    (ended_at, self._info.total_frames, self._info.anomaly_count,
                     self._info.event_clip_count, self._session_id),
                )
                _safe_commit(self._conn)
            except Exception:
                logger.exception("SessionLogger.stop: error finalising session record")
            finally:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None

        self._info.ended_at_ms = ended_at
        logger.info(
            "Session ended: %s | frames=%d anomalies=%d",
            self._session_id, self._info.total_frames, self._info.anomaly_count,
        )
        return self._info

    # ------------------------------------------------------------------
    # Writers (all thread-safe via _lock)
    # ------------------------------------------------------------------

    def log_measurement(self, m: Measurement) -> None:
        if self._conn is None:
            return
        bbox_str = str(m.wire_bbox) if m.wire_bbox else None
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO measurements "
                    "(session_id,frame_id,timestamp_ms,stagger_mm,"
                    "diameter_mm,confidence,wire_bbox) VALUES (?,?,?,?,?,?,?)",
                    (self._session_id, m.frame_id, m.timestamp_ms,
                     m.stagger_mm, m.diameter_mm, m.confidence, bbox_str),
                )
                _safe_commit(self._conn)
            except Exception:
                logger.exception("log_measurement: write failed (frame %d)", m.frame_id)
        if self._info:
            self._info.total_frames += 1

    def log_anomaly(self, a: "Anomaly") -> int:
        """Write an anomaly to SQLite.  Returns the SQLite rowid of the new row."""
        if self._conn is None:
            return -1
        rowid = -1
        with self._lock:
            try:
                cur = self._conn.execute(
                    """
                    INSERT INTO anomalies
                        (session_id, frame_id, timestamp_ms, anomaly_type, value,
                         threshold, severity, message, latitude, longitude,
                         speed_kmh, video_clip, model_version)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        self._session_id, a.frame_id, a.timestamp_ms,
                        a.anomaly_type, a.value, a.threshold, a.severity,
                        a.message, a.latitude, a.longitude, a.speed_kmh,
                        a.video_clip, a.model_version,
                    ),
                )
                _safe_commit(self._conn)
                rowid = cur.lastrowid or -1
            except Exception:
                logger.exception("log_anomaly: write failed (frame %d)", a.frame_id)
        if self._info:
            self._info.anomaly_count += 1
        return rowid

    def update_anomaly_clip(self, anomaly_rowid: int, clip_path: str) -> None:
        """Backfill the video_clip path once the clip file has been written."""
        if self._conn is None or anomaly_rowid < 0:
            return
        with self._lock:
            try:
                self._conn.execute(
                    "UPDATE anomalies SET video_clip=? WHERE id=?",
                    (clip_path, anomaly_rowid),
                )
                _safe_commit(self._conn)
            except Exception:
                logger.exception(
                    "update_anomaly_clip: write failed (rowid %d)", anomaly_rowid
                )
        if self._info:
            self._info.event_clip_count += 1

    @property
    def db_path(self) -> Optional[Path]:
        return self._db_path

    @property
    def session_id(self) -> str:
        return self._session_id

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
"""

from __future__ import annotations

import logging
import sqlite3
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
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT,
    frame_id     INTEGER,
    timestamp_ms REAL,
    anomaly_type TEXT,
    value        REAL,
    threshold    REAL,
    severity     TEXT,
    message      TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);
"""


class SessionLogger:
    """Manages a single measurement session: SQLite writer + session metadata."""

    def __init__(self, session_dir: Path, source: str, notes: str = "") -> None:
        self._session_dir = session_dir
        self._source = source
        self._notes = notes
        self._session_id: str = ""
        self._db_path: Optional[Path] = None
        self._conn: Optional[sqlite3.Connection] = None
        self._info: Optional[SessionInfo] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> SessionInfo:
        """Open a new session and create the SQLite database."""
        self._session_dir.mkdir(parents=True, exist_ok=True)
        ts = time.strftime("%Y%m%dT%H%M%S")
        self._session_id = f"{ts}_{uuid.uuid4().hex[:6]}"
        self._db_path = self._session_dir / f"{self._session_id}.sqlite"

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.executescript(_DDL)
        self._conn.commit()

        started_at = time.time() * 1000
        self._conn.execute(
            "INSERT INTO sessions (session_id, source, started_at_ms, notes) VALUES (?,?,?,?)",
            (self._session_id, self._source, started_at, self._notes),
        )
        self._conn.commit()

        self._info = SessionInfo(
            session_id=self._session_id,
            source=self._source,
            started_at_ms=started_at,
            notes=self._notes,
        )
        logger.info("Session started: %s → %s", self._session_id, self._db_path)
        return self._info

    def stop(self) -> SessionInfo:
        """Close the session and finalize the database record."""
        if self._conn is None or self._info is None:
            raise RuntimeError("Session not started.")
        ended_at = time.time() * 1000
        self._conn.execute(
            "UPDATE sessions SET ended_at_ms=?, total_frames=?, anomaly_count=? WHERE session_id=?",
            (ended_at, self._info.total_frames, self._info.anomaly_count, self._session_id),
        )
        self._conn.commit()
        self._conn.close()
        self._conn = None
        self._info.ended_at_ms = ended_at
        logger.info("Session ended: %s | frames=%d anomalies=%d",
                    self._session_id, self._info.total_frames, self._info.anomaly_count)
        return self._info

    # ------------------------------------------------------------------
    # Writers
    # ------------------------------------------------------------------

    def log_measurement(self, m: Measurement) -> None:
        if self._conn is None:
            return
        bbox_str = str(m.wire_bbox) if m.wire_bbox else None
        self._conn.execute(
            "INSERT INTO measurements (session_id,frame_id,timestamp_ms,stagger_mm,diameter_mm,confidence,wire_bbox) VALUES (?,?,?,?,?,?,?)",
            (self._session_id, m.frame_id, m.timestamp_ms, m.stagger_mm, m.diameter_mm, m.confidence, bbox_str),
        )
        self._conn.commit()
        if self._info:
            self._info.total_frames += 1

    def log_anomaly(self, a: Anomaly) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "INSERT INTO anomalies (session_id,frame_id,timestamp_ms,anomaly_type,value,threshold,severity,message) VALUES (?,?,?,?,?,?,?,?)",
            (self._session_id, a.frame_id, a.timestamp_ms, a.anomaly_type, a.value, a.threshold, a.severity, a.message),
        )
        self._conn.commit()
        if self._info:
            self._info.anomaly_count += 1

    @property
    def db_path(self) -> Optional[Path]:
        return self._db_path

    @property
    def session_id(self) -> str:
        return self._session_id

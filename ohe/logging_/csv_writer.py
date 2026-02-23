"""
logging_/csv_writer.py
-----------------------
Rolling CSV writer for per-frame measurements.

Each row contains: session_id, frame_id, timestamp_ms, stagger_mm,
diameter_mm, confidence, anomaly_types (semicolon-separated if any).

Rolls over to a new file when ``max_rows`` is reached.
"""

from __future__ import annotations

import csv
import logging
import time
from pathlib import Path
from typing import Optional

from ohe.core.models import Anomaly, Measurement

logger = logging.getLogger(__name__)

_FIELDNAMES = [
    "session_id",
    "frame_id",
    "timestamp_ms",
    "stagger_mm",
    "diameter_mm",
    "confidence",
    "anomaly_types",
    "anomaly_severities",
]


class CsvWriter:
    """Writes measurements to rolling CSV files."""

    def __init__(self, session_dir: Path, session_id: str, max_rows: int = 100_000) -> None:
        self._session_dir = session_dir
        self._session_id = session_id
        self._max_rows = max_rows
        self._row_count = 0
        self._file_index = 0
        self._file: Optional[object] = None
        self._writer: Optional[csv.DictWriter] = None
        self._open_new_file()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, m: Measurement, anomalies: list[Anomaly] | None = None) -> None:
        """Append one measurement row to the current CSV file."""
        if self._writer is None:
            return
        anomalies = anomalies or []
        row = {
            "session_id": self._session_id,
            "frame_id": m.frame_id,
            "timestamp_ms": f"{m.timestamp_ms:.3f}",
            "stagger_mm": f"{m.stagger_mm:.4f}" if m.stagger_mm is not None else "",
            "diameter_mm": f"{m.diameter_mm:.4f}" if m.diameter_mm is not None else "",
            "confidence": f"{m.confidence:.4f}",
            "anomaly_types": ";".join(a.anomaly_type for a in anomalies),
            "anomaly_severities": ";".join(a.severity for a in anomalies),
        }
        self._writer.writerow(row)
        self._row_count += 1

        if self._row_count >= self._max_rows:
            self.close()
            self._file_index += 1
            self._row_count = 0
            self._open_new_file()

    def flush(self) -> None:
        if self._file:
            self._file.flush()  # type: ignore[attr-defined]

    def close(self) -> None:
        if self._file:
            self._file.close()  # type: ignore[attr-defined]
            self._file = None
            self._writer = None
            logger.debug("CSV file closed (session=%s, part=%d)", self._session_id, self._file_index)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _open_new_file(self) -> None:
        suffix = f"_part{self._file_index:03d}" if self._file_index > 0 else ""
        filename = f"{self._session_id}{suffix}.csv"
        path = self._session_dir / filename
        self._file = open(path, "w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=_FIELDNAMES)  # type: ignore[arg-type]
        self._writer.writeheader()
        logger.info("CSV writer opened: %s", path)

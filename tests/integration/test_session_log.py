"""tests/integration/test_session_log.py — Full pipeline → SQLite integration test."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import numpy as np
import pytest

from ohe.core.config import load_config
from ohe.core.models import Measurement, RawFrame
from ohe.logging_.csv_writer import CsvWriter
from ohe.logging_.export import SessionExporter
from ohe.logging_.log_worker import LogWorker
from ohe.logging_.session import SessionLogger
from ohe.processing.calibration import CalibrationModel
from ohe.processing.pipeline import ProcessingPipeline
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def make_wire_frame(w=800, h=200, wire_y=100, frame_id=0) -> RawFrame:
    """Synthetic BGR frame with a bright horizontal wire band."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[wire_y - 3: wire_y + 4, :] = 220
    return RawFrame(frame_id=frame_id, timestamp_ms=frame_id * 33.3, image=img, source="test_integration")


class TestSessionLogIntegration:
    """Verify that measurements flow from the pipeline all the way into SQLite."""

    def setup_method(self):
        self.cfg = load_config()
        self.cfg.processing.roi = None
        self.cfg.processing.min_detection_confidence = 0.0
        self.cfg.processing.canny_threshold1 = 30
        self.cfg.processing.canny_threshold2 = 100
        self.cfg.processing.hough_threshold = 15
        self.cfg.processing.hough_min_line_length = 20
        self.cal = CalibrationModel(
            px_per_mm=10.0, track_centre_x_px=400,
            image_width_px=800, image_height_px=200,
        )
        self.pipeline = ProcessingPipeline(self.cfg, self.cal)
        self.rules = RulesEngine(Thresholds.from_config(self.cfg.rules))

    def test_measurements_written_to_sqlite(self, tmp_path):
        """5 synthetic frames → 5 rows in measurements table."""
        session = SessionLogger(tmp_path, source="test", notes="integration")
        info = session.start()

        worker = LogWorker(session, csv_writer=None)
        worker.start()

        for i in range(5):
            raw = make_wire_frame(frame_id=i)
            m = self.pipeline.run(raw)
            anomalies = self.rules.evaluate(m)
            worker.push_measurement(m, anomalies)

        worker.stop()
        session.stop()

        # Verify SQLite contents
        conn = sqlite3.connect(str(session.db_path))
        rows = conn.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        conn.close()
        assert rows == 5, f"Expected 5 measurement rows, got {rows}"

    def test_session_row_created(self, tmp_path):
        """A sessions row must exist with correct source."""
        session = SessionLogger(tmp_path, source="my_video.mp4")
        info = session.start()
        session.stop()

        conn = sqlite3.connect(str(session.db_path))
        row = conn.execute("SELECT source, total_frames FROM sessions").fetchone()
        conn.close()
        assert row is not None
        assert "my_video.mp4" in row[0]

    def test_csv_writer_produces_file(self, tmp_path):
        """CsvWriter must create a .csv file with the correct header."""
        session = SessionLogger(tmp_path, source="test")
        info = session.start()
        csv = CsvWriter(tmp_path, info.session_id, max_rows=1000)
        worker = LogWorker(session, csv_writer=csv)
        worker.start()

        m = Measurement(0, 0.0, stagger_mm=50.0, diameter_mm=12.0, confidence=0.9)
        worker.push_measurement(m)
        worker.stop()
        csv.close()
        session.stop()

        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1
        content = csv_files[0].read_text(encoding="utf-8")
        assert "stagger_mm" in content   # header
        assert "50.0000" in content      # value

    def test_export_csv_from_session(self, tmp_path):
        """SessionExporter.export_csv() must produce a CSV with measurement data."""
        session = SessionLogger(tmp_path, source="test_export")
        info = session.start()
        worker = LogWorker(session, csv_writer=None)
        worker.start()

        for i in range(3):
            m = Measurement(i, i * 33.3, stagger_mm=float(i * 10), diameter_mm=12.0, confidence=0.9)
            worker.push_measurement(m)

        worker.stop()
        session.stop()

        exporter = SessionExporter(session.db_path)
        csv_path = exporter.export_csv()
        assert csv_path.exists()
        lines = csv_path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 4  # header + 3 data rows

    def test_export_summary_json(self, tmp_path):
        """SessionExporter.export_summary_json() must produce valid JSON with expected keys."""
        import json
        session = SessionLogger(tmp_path, source="test_json")
        info = session.start()
        worker = LogWorker(session, csv_writer=None)
        worker.start()

        m = Measurement(0, 0.0, stagger_mm=100.0, diameter_mm=12.0, confidence=0.85)
        worker.push_measurement(m)
        worker.stop()
        session.stop()

        exporter = SessionExporter(session.db_path)
        json_path = exporter.export_summary_json()
        summary = json.loads(json_path.read_text(encoding="utf-8"))

        assert "session" in summary
        assert "detection" in summary
        assert "stagger_mm" in summary
        assert summary["stagger_mm"]["avg"] == pytest.approx(100.0, rel=1e-3)

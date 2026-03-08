"""tests/unit/test_events_export.py — Tests for export_events_json() and updated export_csv()."""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from ohe.core.models import Anomaly, Measurement
from ohe.logging_.export import SessionExporter
from ohe.logging_.log_worker import LogWorker
from ohe.logging_.session import SessionLogger


def _make_anomaly(frame_id: int = 0) -> Anomaly:
    return Anomaly(
        frame_id=frame_id,
        timestamp_ms=frame_id * 33.3,
        anomaly_type="STAGGER_RIGHT",
        value=160.0,
        threshold=150.0,
        severity="WARNING",
        message="Test anomaly",
        latitude=28.6139,
        longitude=77.2090,
        speed_kmh=60.0,
        video_clip="events/event_001.mp4",
        model_version="classical-v1",
    )


def _make_measurement(frame_id: int = 0) -> Measurement:
    return Measurement(
        frame_id=frame_id,
        timestamp_ms=frame_id * 33.3,
        stagger_mm=160.0,
        diameter_mm=12.0,
        confidence=0.85,
    )


class TestEventsExport:
    def _setup_session(self, tmp_path, n_anomalies=3):
        session = SessionLogger(tmp_path, source="test_events")
        info = session.start()
        # Write measurements + anomalies directly (no LogWorker) to avoid
        # SQLite threading issues in the test harness
        for i in range(n_anomalies):
            m = _make_measurement(i)
            a = _make_anomaly(i)
            session.log_measurement(m)
            session.log_anomaly(a)
        session.stop()
        return session

    def test_export_events_json_created(self, tmp_path):
        session = self._setup_session(tmp_path, n_anomalies=3)
        exporter = SessionExporter(session.db_path)
        path = exporter.export_events_json()
        assert path.exists()

    def test_export_events_json_has_required_fields(self, tmp_path):
        session = self._setup_session(tmp_path, n_anomalies=2)
        exporter = SessionExporter(session.db_path)
        path = exporter.export_events_json()
        events = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(events, list)
        assert len(events) == 2
        for e in events:
            assert "event_id"          in e
            assert "timestamp"         in e
            assert "frame_number"      in e
            assert "latitude"          in e
            assert "longitude"         in e
            assert "vehicle_speed_kmh" in e
            assert "anomaly_type"      in e
            assert "severity"          in e
            assert "video_clip"        in e
            assert "model_version"     in e

    def test_export_events_json_values(self, tmp_path):
        session = self._setup_session(tmp_path, n_anomalies=1)
        exporter = SessionExporter(session.db_path)
        path = exporter.export_events_json()
        events = json.loads(path.read_text(encoding="utf-8"))
        e = events[0]
        assert e["latitude"] == pytest.approx(28.6139, rel=1e-4)
        assert e["longitude"] == pytest.approx(77.2090, rel=1e-4)
        assert e["vehicle_speed_kmh"] == pytest.approx(60.0, rel=1e-2)
        assert e["anomaly_type"] == "STAGGER_RIGHT"
        assert e["model_version"] == "classical-v1"
        assert e["video_clip"] == "events/event_001.mp4"

    def test_export_csv_includes_geo_columns(self, tmp_path):
        session = self._setup_session(tmp_path, n_anomalies=1)
        exporter = SessionExporter(session.db_path)
        csv_path = exporter.export_csv()
        content = csv_path.read_text(encoding="utf-8")
        assert "latitude"  in content
        assert "longitude" in content
        assert "speed_kmh" in content
        assert "video_clip" in content

    def test_export_all_returns_three_paths(self, tmp_path):
        session = self._setup_session(tmp_path, n_anomalies=1)
        exporter = SessionExporter(session.db_path)
        result = exporter.export_all()
        assert len(result) == 3
        csv_path, json_path, events_path = result
        assert csv_path.exists()
        assert json_path.exists()
        assert events_path.exists()

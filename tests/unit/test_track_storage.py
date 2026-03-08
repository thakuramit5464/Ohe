"""tests/unit/test_track_storage.py — Unit tests for track-scoped directory helpers."""
from __future__ import annotations

import pytest
from pathlib import Path

from ohe.core.config import load_config


class TestTrackStorage:
    def test_track_dir_path_contains_name(self, tmp_path, monkeypatch):
        """track_dir_path() should embed the track name in the returned path."""
        cfg = load_config()
        # Patch _PROJECT_ROOT so paths stay inside tmp_path
        import ohe.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
        track_path = cfg.track_dir_path("Nairobi_Test_01")
        assert "Nairobi_Test_01" in str(track_path)

    def test_ensure_track_dirs_creates_subdirs(self, tmp_path, monkeypatch):
        """ensure_track_dirs() should create events/, logs/, reports/, videos/."""
        cfg = load_config()
        import ohe.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
        root = cfg.ensure_track_dirs("Test_Run_01")
        for sub in ("events", "logs", "reports", "videos"):
            assert (root / sub).is_dir(), f"Missing sub-dir: {sub}"

    def test_ensure_track_dirs_idempotent(self, tmp_path, monkeypatch):
        """Calling ensure_track_dirs() twice should not raise."""
        cfg = load_config()
        import ohe.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
        cfg.ensure_track_dirs("Repeat_Run")
        cfg.ensure_track_dirs("Repeat_Run")   # second call should not fail

    def test_different_tracks_separate_dirs(self, tmp_path, monkeypatch):
        """Two different track names should produce two distinct paths."""
        cfg = load_config()
        import ohe.core.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "_PROJECT_ROOT", tmp_path)
        p1 = cfg.track_dir_path("TrackA")
        p2 = cfg.track_dir_path("TrackB")
        assert p1 != p2

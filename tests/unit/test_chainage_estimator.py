"""
tests/unit/test_chainage_estimator.py
---------------------------------------
Unit tests for ChainageEstimator.
"""

from __future__ import annotations

import pytest

from ohe.core.config import ChainageConfig
from ohe.processing.chainage_estimator import ChainageEstimator


def _config(speed_kmh: float = 60.0, initial_m: float = 0.0) -> ChainageConfig:
    return ChainageConfig(
        speed_source="config",
        simulated_speed_kmh=speed_kmh,
        initial_chainage_m=initial_m,
    )


_KMH_TO_MS = 1.0 / 3.6   # same constant as in the module


class TestChainageEstimator:
    def test_initial_chainage_zero(self):
        est = ChainageEstimator(_config(initial_m=0.0))
        # First call — no Δt yet, should return 0
        ch = est.update(timestamp_ms=0.0)
        assert ch == pytest.approx(0.0)

    def test_initial_chainage_offset(self):
        est = ChainageEstimator(_config(initial_m=500.0))
        ch = est.update(timestamp_ms=0.0)
        assert ch == pytest.approx(500.0)

    def test_advances_correctly_after_one_frame(self):
        """After Δt = 1 s at 60 km/h the estimator should advance 16.667 m."""
        est = ChainageEstimator(_config(speed_kmh=60.0))
        est.update(timestamp_ms=0.0)      # first call — no movement
        ch = est.update(timestamp_ms=1000.0)   # 1000 ms = 1 s
        expected = 60.0 * _KMH_TO_MS * 1.0
        assert ch == pytest.approx(expected, rel=1e-4)

    def test_advances_over_multiple_frames(self):
        """Total chainage after N frames should equal speed × total_time."""
        speed_kmh = 72.0
        est = ChainageEstimator(_config(speed_kmh=speed_kmh))
        n_frames = 25
        frame_ms  = 40.0    # 25 fps
        for i in range(n_frames + 1):
            ch = est.update(timestamp_ms=i * frame_ms)
        total_s = n_frames * frame_ms / 1000.0
        expected = speed_kmh * _KMH_TO_MS * total_s
        assert ch == pytest.approx(expected, rel=1e-3)

    def test_zero_speed_no_advance(self):
        est = ChainageEstimator(_config(speed_kmh=0.0))
        est.update(timestamp_ms=0.0)
        ch = est.update(timestamp_ms=5000.0)
        assert ch == pytest.approx(0.0)

    def test_register_mast_returns_none_first_time(self):
        est = ChainageEstimator(_config())
        est.update(timestamp_ms=0.0)
        spacing = est.register_mast()
        assert spacing is None

    def test_register_mast_calculates_spacing(self):
        est = ChainageEstimator(_config(speed_kmh=36.0))  # 10 m/s
        est.update(timestamp_ms=0.0)
        est.register_mast()   # first mast at chainage = 0

        # Advance 4 s → 40 m
        for t in range(1, 5):
            est.update(timestamp_ms=float(t * 1000))

        spacing = est.register_mast()   # second mast
        assert spacing == pytest.approx(40.0, rel=1e-2)

    def test_last_mast_chainage_updated(self):
        est = ChainageEstimator(_config(speed_kmh=36.0))
        est.update(timestamp_ms=0.0)
        est.register_mast()
        est.update(timestamp_ms=2000.0)
        est.register_mast()
        # last_mast_chainage should now be ~20 m
        assert est.last_mast_chainage_m == pytest.approx(20.0, rel=1e-2)

    def test_reset_restores_initial_chainage(self):
        est = ChainageEstimator(_config(speed_kmh=60.0, initial_m=0.0))
        for t in range(0, 5001, 1000):
            est.update(timestamp_ms=float(t))
        assert est.chainage_m > 0
        est.reset(initial_m=1000.0)
        assert est.chainage_m == pytest.approx(1000.0)
        assert est.last_mast_chainage_m is None

    def test_override_speed_kwarg_used_when_pipeline_source(self):
        """When speed_source == 'config', override kwarg is still used
        if provided, because pipeline mode should respect external speed."""
        cfg = ChainageConfig(
            speed_source="pipeline",
            simulated_speed_kmh=10.0,
            initial_chainage_m=0.0,
        )
        est = ChainageEstimator(cfg)
        est.update(timestamp_ms=0.0)
        ch = est.update(timestamp_ms=1000.0, speed_kmh=36.0)   # 10 m/s
        assert ch == pytest.approx(10.0, rel=1e-2)

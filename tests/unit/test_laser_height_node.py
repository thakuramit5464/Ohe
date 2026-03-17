"""
tests/unit/test_laser_height_node.py
--------------------------------------
Unit tests for LaserHeightNode.
"""

from __future__ import annotations

import pytest

from ohe.core.config import LaserHeightConfig
from ohe.processing.laser_height_node import LaserHeightNode


def _simulated_config(nominal: float = 5.25, noise: float = 0.015) -> LaserHeightConfig:
    return LaserHeightConfig(
        mode="simulated",
        sensor_mount_height_m=6.5,
        nominal_height_m=nominal,
        noise_std_m=noise,
    )


def _real_config(mount: float = 6.5) -> LaserHeightConfig:
    return LaserHeightConfig(
        mode="real",
        sensor_mount_height_m=mount,
        nominal_height_m=5.25,
        noise_std_m=0.0,
    )


class TestLaserHeightNodeSimulated:
    def test_returns_value_near_nominal(self):
        node = LaserHeightNode(_simulated_config(nominal=5.25, noise=0.0))
        h = node.get_height(timestamp_ms=0.0)
        assert h == pytest.approx(5.25, abs=1e-6)

    def test_noise_spread_within_5_sigma(self):
        """Monte-Carlo: 200 draws should all be within ±5σ of nominal.

        Using 5σ (probability of exceeding ≈ 3e-7 per draw) rather than 3σ
        to keep the test deterministic without fixing the RNG seed.
        """
        nominal, sigma = 5.25, 0.015
        node = LaserHeightNode(_simulated_config(nominal=nominal, noise=sigma))
        limit = 5 * sigma   # 5σ ≈ effectively impossible to exceed
        for i in range(200):
            h = node.get_height(timestamp_ms=float(i * 40))
            assert h is not None
            assert abs(h - nominal) <= limit + 1e-9, (
                f"Height {h:.4f} outside ±5σ band [{nominal - limit:.4f}, {nominal + limit:.4f}]"
            )

    def test_returns_float(self):
        node = LaserHeightNode(_simulated_config())
        h = node.get_height(timestamp_ms=0.0)
        assert isinstance(h, float)

    def test_last_height_updated(self):
        node = LaserHeightNode(_simulated_config(noise=0.0, nominal=5.0))
        assert node.last_height_m is None
        node.get_height(timestamp_ms=0.0)
        assert node.last_height_m == pytest.approx(5.0, abs=1e-6)


class TestLaserHeightNodeReal:
    def test_computes_height_correctly(self):
        """wire_height = mount_height - measured_distance"""
        node = LaserHeightNode(_real_config(mount=6.5))
        h = node.get_height(timestamp_ms=0.0, raw_distance_m=1.3)
        assert h == pytest.approx(6.5 - 1.3, rel=1e-6)

    def test_returns_none_when_no_reading(self):
        node = LaserHeightNode(_real_config())
        h = node.get_height(timestamp_ms=0.0, raw_distance_m=None)
        assert h is None

    def test_rejects_negative_distance(self):
        node = LaserHeightNode(_real_config())
        h = node.get_height(timestamp_ms=0.0, raw_distance_m=-0.5)
        assert h is None

    def test_clamps_height_to_zero_on_excessive_distance(self):
        """If sensor distance > mount height the computed height would be negative — clamp to 0."""
        node = LaserHeightNode(_real_config(mount=2.0))
        h = node.get_height(timestamp_ms=0.0, raw_distance_m=5.0)
        assert h == pytest.approx(0.0)

    def test_exact_mount_height_distance_gives_zero(self):
        mount = 6.5
        node = LaserHeightNode(_real_config(mount=mount))
        h = node.get_height(timestamp_ms=0.0, raw_distance_m=mount)
        assert h == pytest.approx(0.0, abs=1e-6)

    def test_simulated_distance_not_used_in_real_mode(self):
        """In real mode, passing None should return None, not a simulated fallback."""
        node = LaserHeightNode(_real_config())
        h = node.get_height(timestamp_ms=0.0)   # raw_distance_m defaults to None
        assert h is None

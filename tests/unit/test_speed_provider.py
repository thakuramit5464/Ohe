"""tests/unit/test_speed_provider.py — Unit tests for SpeedProvider."""
from __future__ import annotations

import pytest
from ohe.speed.provider import NullSpeedProvider, SimulatedSpeedProvider


class TestNullSpeedProvider:
    def test_returns_zero(self):
        p = NullSpeedProvider()
        assert p.get_speed(0, 0.0) == 0.0

    def test_always_zero(self):
        p = NullSpeedProvider()
        for i in range(20):
            assert p.get_speed(i, float(i * 33)) == 0.0


class TestSimulatedSpeedProvider:
    def test_returns_float(self):
        p = SimulatedSpeedProvider(base_speed_kmh=60.0, jitter_kmh=5.0)
        speed = p.get_speed(0, 0.0)
        assert isinstance(speed, float)

    def test_speed_near_base(self):
        """Speed should stay within base ± 2*jitter."""
        p = SimulatedSpeedProvider(base_speed_kmh=60.0, jitter_kmh=5.0)
        for i in range(100):
            speed = p.get_speed(i, float(i * 33))
            assert 0.0 <= speed <= 70.0, f"Speed out of range: {speed}"

    def test_speed_never_negative(self):
        p = SimulatedSpeedProvider(base_speed_kmh=5.0, jitter_kmh=3.0)
        for i in range(200):
            assert p.get_speed(i, 0.0) >= 0.0

    def test_zero_jitter_returns_base(self):
        """With zero jitter, speed should stay very close to base speed."""
        p = SimulatedSpeedProvider(base_speed_kmh=80.0, jitter_kmh=0.0)
        speeds = [p.get_speed(i, 0.0) for i in range(50)]
        assert all(79.0 <= s <= 81.0 for s in speeds), f"Speeds out of range: {speeds}"

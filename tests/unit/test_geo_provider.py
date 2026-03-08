"""tests/unit/test_geo_provider.py — Unit tests for the geolocation provider."""
from __future__ import annotations

import time
import pytest

from ohe.geo.provider import NullGeoProvider, SimulatedGeoProvider
from ohe.core.models import GeoLocation


class TestNullGeoProvider:
    def test_returns_none(self):
        provider = NullGeoProvider()
        result = provider.get_location(frame_id=0, timestamp_ms=0.0)
        assert result is None


class TestSimulatedGeoProvider:
    def test_returns_geo_location(self):
        provider = SimulatedGeoProvider(
            origin_latitude=28.6139,
            origin_longitude=77.2090,
            speed_kmh=60.0,
        )
        loc = provider.get_location(frame_id=0, timestamp_ms=0.0)
        assert isinstance(loc, GeoLocation)

    def test_latitude_near_origin_at_start(self):
        provider = SimulatedGeoProvider(
            origin_latitude=28.6139,
            origin_longitude=77.2090,
            speed_kmh=60.0,
        )
        loc = provider.get_location(frame_id=0, timestamp_ms=0.0)
        # Should be very close to origin since almost no time has elapsed
        assert abs(loc.latitude - 28.6139) < 0.01
        assert abs(loc.longitude - 77.2090) < 0.001

    def test_speed_kmh_preserved(self):
        provider = SimulatedGeoProvider(speed_kmh=80.0)
        loc = provider.get_location(frame_id=5, timestamp_ms=100.0)
        assert loc.speed_kmh == 80.0

    def test_latitude_increases_over_time(self):
        """Simulated vehicle should move north (increasing latitude)."""
        provider = SimulatedGeoProvider(
            origin_latitude=28.6139,
            origin_longitude=77.2090,
            speed_kmh=60.0,
        )
        loc1 = provider.get_location(frame_id=0, timestamp_ms=0.0)
        time.sleep(0.05)  # wait 50ms so some movement accumulates
        loc2 = provider.get_location(frame_id=30, timestamp_ms=1000.0)
        assert loc2.latitude >= loc1.latitude

    def test_timestamp_iso_format(self):
        provider = SimulatedGeoProvider()
        loc = provider.get_location(frame_id=0, timestamp_ms=0.0)
        # Should be parseable as ISO date
        import datetime
        datetime.datetime.strptime(loc.timestamp_iso, "%Y-%m-%dT%H:%M:%S")

    def test_geo_location_as_dict(self):
        loc = GeoLocation(latitude=28.6, longitude=77.2, speed_kmh=60.0, timestamp_iso="2026-03-08T10:00:00")
        d = loc.as_dict()
        assert d["latitude"] == 28.6
        assert d["longitude"] == 77.2
        assert d["speed_kmh"] == 60.0
        assert d["timestamp"] == "2026-03-08T10:00:00"

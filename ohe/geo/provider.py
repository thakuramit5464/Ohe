"""
geo/provider.py
---------------
Geolocation provider abstraction for the OHE pipeline.

Two implementations are provided:

* :class:`NullGeoProvider`       — used when ``geo.enabled = False``; always
                                   returns ``None`` so no geo data is attached.
* :class:`SimulatedGeoProvider`  — returns deterministic coordinates that drift
                                   linearly from a configurable origin point.
                                   Useful for demos and testing until a real GPS
                                   feed is available.

To integrate a real GPS receiver (e.g. NMEA serial port, GPSD socket, REST API),
subclass :class:`GeoProvider` and implement ``get_location()``.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Optional

from ohe.core.models import GeoLocation


class GeoProvider(ABC):
    """Abstract base for geolocation data sources."""

    @abstractmethod
    def get_location(self, frame_id: int, timestamp_ms: float) -> Optional[GeoLocation]:
        """Return a :class:`GeoLocation` for the given frame, or ``None``."""
        ...


class NullGeoProvider(GeoProvider):
    """No-op provider — always returns None."""

    def get_location(self, frame_id: int, timestamp_ms: float) -> Optional[GeoLocation]:
        return None


class SimulatedGeoProvider(GeoProvider):
    """
    Simulates a vehicle moving north from ``origin`` at a fixed speed.

    Latitude increases by ≈ 1° per 111 km, so:
        Δlat ≈ speed_kmh * elapsed_hours / 111.0

    The provider is intentionally simple — it just needs to produce plausible
    lat/lon values so the rest of the pipeline can be tested end-to-end.
    """

    # 1 degree of latitude ≈ 111.0 km
    _KM_PER_DEG_LAT: float = 111.0

    def __init__(
        self,
        origin_latitude: float = 28.6139,
        origin_longitude: float = 77.2090,
        speed_kmh: float = 60.0,
    ) -> None:
        self._origin_lat  = origin_latitude
        self._origin_lon  = origin_longitude
        self._speed_kmh   = speed_kmh
        self._start_time  = time.monotonic()

    # ------------------------------------------------------------------
    # GeoProvider implementation
    # ------------------------------------------------------------------

    def get_location(self, frame_id: int, timestamp_ms: float) -> GeoLocation:
        elapsed_s   = time.monotonic() - self._start_time
        elapsed_h   = elapsed_s / 3600.0
        distance_km = self._speed_kmh * elapsed_h

        delta_lat = distance_km / self._KM_PER_DEG_LAT
        lat = self._origin_lat + delta_lat
        lon = self._origin_lon  # travelling due north → longitude stays fixed

        import datetime
        ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        return GeoLocation(
            latitude=round(lat, 6),
            longitude=round(lon, 6),
            speed_kmh=self._speed_kmh,
            timestamp_iso=ts,
        )

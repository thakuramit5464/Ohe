"""
speed/provider.py
-----------------
Vehicle speed provider abstraction for the OHE pipeline.

Two implementations:

* :class:`NullSpeedProvider`        — returns 0.0; used when speed is disabled.
* :class:`SimulatedSpeedProvider`   — returns a configurable base speed with a
                                      small random jitter to simulate real sensor
                                      noise. Suitable for testing without hardware.

To use a real speed source (CAN bus, telemetry API, etc.), subclass
:class:`SpeedProvider` and implement ``get_speed()``.
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod


class SpeedProvider(ABC):
    """Abstract base for vehicle speed data sources."""

    @abstractmethod
    def get_speed(self, frame_id: int, timestamp_ms: float) -> float:
        """Return current vehicle speed in km/h."""
        ...


class NullSpeedProvider(SpeedProvider):
    """Always returns 0.0 — used when speed is disabled or not configured."""

    def get_speed(self, frame_id: int, timestamp_ms: float) -> float:
        return 0.0


class SimulatedSpeedProvider(SpeedProvider):
    """
    Returns a realistic simulated vehicle speed.

    The speed varies around ``base_speed_kmh`` by ±``jitter_kmh`` using a
    small random walk, clamped to [0, base + 2*jitter].  This gives gently
    fluctuating readings like a real speedometer.

    Parameters
    ----------
    base_speed_kmh:  Central speed value in km/h (default 60).
    jitter_kmh:      Maximum random variation per frame (default 5).
    """

    def __init__(
        self,
        base_speed_kmh: float = 60.0,
        jitter_kmh: float = 5.0,
    ) -> None:
        self._base        = base_speed_kmh
        self._jitter      = jitter_kmh
        self._current     = base_speed_kmh
        self._rng         = random.Random()

    def get_speed(self, frame_id: int, timestamp_ms: float) -> float:
        """Return a jittered speed value (km/h)."""
        step = self._rng.uniform(-self._jitter * 0.3, self._jitter * 0.3)
        self._current += step
        # Gradually pull back towards base speed
        self._current += (self._base - self._current) * 0.05
        # Clamp
        self._current = max(0.0, min(self._current, self._base + 2 * self._jitter))
        return round(self._current, 1)

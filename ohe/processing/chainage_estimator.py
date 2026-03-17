"""
processing/chainage_estimator.py
---------------------------------
Estimates the track chainage (distance travelled along track in metres).

Usage
-----
    estimator = ChainageEstimator(config.chainage)
    estimator.reset(initial_m=0.0)

    for frame in frames:
        chainage = estimator.update(
            timestamp_ms=frame.timestamp_ms,
            speed_kmh=speed_provider.get(),   # optional override
        )

    # When a mast is confirmed:
    mast_spacing = estimator.register_mast()

Modes
-----
* ``speed_source == "config"``    — uses ``simulated_speed_kmh`` from config
* ``speed_source == "pipeline"``  — caller passes the actual speed per frame
"""

from __future__ import annotations

import logging
from typing import Optional

from ohe.core.config import ChainageConfig

logger = logging.getLogger(__name__)

# 1 km/h = 1000/3600 m/s
_KMH_TO_MS = 1.0 / 3.6


class ChainageEstimator:
    """Accumulates metres-travelled using speed × Δt integration."""

    def __init__(self, config: ChainageConfig) -> None:
        self._cfg = config
        self._chainage_m: float = config.initial_chainage_m
        self._last_timestamp_ms: Optional[float] = None
        self._last_mast_chainage_m: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def reset(self, initial_m: float = 0.0) -> None:
        """Reset estimator state (call at session start or track change)."""
        self._chainage_m = initial_m
        self._last_timestamp_ms = None
        self._last_mast_chainage_m = None
        logger.debug("ChainageEstimator reset to %.1f m", initial_m)

    def update(
        self,
        timestamp_ms: float,
        speed_kmh: Optional[float] = None,
    ) -> float:
        """Advance chainage by speed × Δt and return current chainage (m).

        Args:
            timestamp_ms: Current frame timestamp in milliseconds.
            speed_kmh:    Override speed in km/h.  When None and
                          ``speed_source == "config"``, the configured
                          ``simulated_speed_kmh`` is used.

        Returns:
            Current chainage in metres.
        """
        if self._last_timestamp_ms is not None:
            dt_ms = max(0.0, timestamp_ms - self._last_timestamp_ms)
            dt_s  = dt_ms / 1000.0

            if speed_kmh is None or self._cfg.speed_source == "config":
                speed_kmh = self._cfg.simulated_speed_kmh

            self._chainage_m += speed_kmh * _KMH_TO_MS * dt_s

        self._last_timestamp_ms = timestamp_ms
        return self._chainage_m

    @property
    def chainage_m(self) -> float:
        """Current chainage in metres (read-only)."""
        return self._chainage_m

    @property
    def last_mast_chainage_m(self) -> Optional[float]:
        """Chainage of the most recently confirmed mast, or None."""
        return self._last_mast_chainage_m

    def register_mast(self) -> Optional[float]:
        """Record that a mast was confirmed at the current chainage.

        Returns:
            Mast spacing (metres) from the previous mast, or ``None`` if this
            is the first mast event in the session.
        """
        spacing: Optional[float] = None
        if self._last_mast_chainage_m is not None:
            spacing = self._chainage_m - self._last_mast_chainage_m
            logger.info(
                "Mast spacing recorded: %.2f m  (chainage %.1f m → %.1f m)",
                spacing, self._last_mast_chainage_m, self._chainage_m,
            )
        else:
            logger.info("First mast registered at chainage %.1f m", self._chainage_m)
        self._last_mast_chainage_m = self._chainage_m
        return spacing

"""
processing/laser_height_node.py
--------------------------------
Wire height measurement provider.

Two modes (selected by ``laser_height.mode`` in config):

Mode A — Simulated (development)
    Returns  ``nominal_height_m + N(0, noise_std_m)``
    Suitable for testing the full pipeline without hardware.

Mode B — Real sensor interface
    Caller provides ``raw_distance_m`` (laser range distance in metres).
    Computes:  ``wire_height_m = sensor_mount_height_m - raw_distance_m``

ROS2 note
---------
In a real deployment this class would be replaced (or wrapped) by a ROS2 node
that subscribes to the sensor topic and calls ``get_height()`` with the
incoming distance message value.
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ohe.core.config import LaserHeightConfig

logger = logging.getLogger(__name__)

_RNG = np.random.default_rng()


class LaserHeightNode:
    """Provides wire height measurements — simulated or real-sensor input."""

    def __init__(self, config: LaserHeightConfig) -> None:
        self._cfg = config
        self._last_height_m: Optional[float] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_height(
        self,
        timestamp_ms: float,
        raw_distance_m: Optional[float] = None,
    ) -> Optional[float]:
        """Return wire height in metres.

        Args:
            timestamp_ms:    Frame timestamp (reserved for future rate-limiting
                             or timestamping; not currently used for computation).
            raw_distance_m:  Distance reading from a real sensor in metres.
                             Required (and used) only in ``mode == "real"``.
                             Ignored in simulated mode.

        Returns:
            Wire height (metres) above rail head, or ``None`` if a real-sensor
            reading was expected but not provided.
        """
        if self._cfg.mode == "simulated":
            height = self._simulated_height()
        else:
            height = self._real_height(raw_distance_m)

        self._last_height_m = height
        return height

    @property
    def last_height_m(self) -> Optional[float]:
        """Most recently returned height (metres)."""
        return self._last_height_m

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _simulated_height(self) -> float:
        """Return nominal height plus Gaussian noise."""
        noise = float(_RNG.normal(0.0, self._cfg.noise_std_m))
        height = self._cfg.nominal_height_m + noise
        logger.debug("Simulated wire height: %.3f m", height)
        return height

    def _real_height(self, raw_distance_m: Optional[float]) -> Optional[float]:
        """Convert raw sensor distance to wire height.

        Formula:
            ``wire_height_m = sensor_mount_height_m - raw_distance_m``

        When the sensor reading is unavailable or negative the method returns
        ``None`` and logs a warning.
        """
        if raw_distance_m is None:
            logger.warning("LaserHeightNode: no sensor reading received (mode=real)")
            return None

        if raw_distance_m <= 0:
            logger.warning(
                "LaserHeightNode: invalid sensor reading %.3f m — skipping",
                raw_distance_m,
            )
            return None

        height = self._cfg.sensor_mount_height_m - raw_distance_m

        if height < 0:
            logger.warning(
                "LaserHeightNode: computed height %.3f m is negative "
                "(mount=%.2f m, distance=%.2f m) — clamped to 0",
                height, self._cfg.sensor_mount_height_m, raw_distance_m,
            )
            height = 0.0

        logger.debug(
            "Real wire height: %.3f m  (mount=%.2f m, distance=%.2f m)",
            height, self._cfg.sensor_mount_height_m, raw_distance_m,
        )
        return height

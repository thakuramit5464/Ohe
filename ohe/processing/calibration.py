"""
processing/calibration.py
-------------------------
Calibration model: pixel-to-millimetre mapping + optional lens undistortion.

The calibration data is stored in ``config/calibration.json`` (see the
default template). The :class:`CalibrationModel` is constructed once and
passed to the Preprocessor and MeasurementEngine.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from ohe.core.exceptions import CalibrationError

logger = logging.getLogger(__name__)


class CalibrationModel:
    """Encapsulates camera geometry and pixel-to-mm scale."""

    def __init__(
        self,
        px_per_mm: float,
        track_centre_x_px: int,
        image_width_px: int,
        image_height_px: int,
        use_undistort: bool = False,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
    ) -> None:
        if px_per_mm <= 0:
            raise CalibrationError(f"px_per_mm must be positive, got {px_per_mm}")
        self.px_per_mm = px_per_mm
        self.track_centre_x_px = track_centre_x_px
        self.image_width_px = image_width_px
        self.image_height_px = image_height_px
        self.use_undistort = use_undistort
        self._camera_matrix = camera_matrix
        self._dist_coeffs = dist_coeffs
        self._map1: Optional[np.ndarray] = None
        self._map2: Optional[np.ndarray] = None

        if use_undistort and camera_matrix is not None and dist_coeffs is not None:
            self._build_undistort_maps()

    # ------------------------------------------------------------------
    # Pixel ↔ mm conversions
    # ------------------------------------------------------------------

    def px_to_mm(self, pixels: float) -> float:
        """Convert a distance in pixels to millimetres."""
        return pixels / self.px_per_mm

    def mm_to_px(self, mm: float) -> float:
        """Convert a distance in millimetres to pixels."""
        return mm * self.px_per_mm

    def stagger_from_centre_px(self, wire_centre_x_px: float) -> float:
        """Return signed stagger in mm.

        Positive = wire to the right of track centre.
        """
        offset_px = wire_centre_x_px - self.track_centre_x_px
        return self.px_to_mm(offset_px)

    # ------------------------------------------------------------------
    # Undistortion
    # ------------------------------------------------------------------

    def undistort(self, image: np.ndarray) -> np.ndarray:
        """Apply pre-computed lens undistortion maps to *image*."""
        if self._map1 is None or self._map2 is None:
            return image
        return cv2.remap(image, self._map1, self._map2, cv2.INTER_LINEAR)

    def _build_undistort_maps(self) -> None:
        size = (self.image_width_px, self.image_height_px)
        self._map1, self._map2 = cv2.initUndistortRectifyMap(
            self._camera_matrix,
            self._dist_coeffs,
            None,
            self._camera_matrix,
            size,
            cv2.CV_16SC2,
        )
        logger.debug("Undistortion maps built for %s", size)

    # ------------------------------------------------------------------
    # Factory: load from JSON
    # ------------------------------------------------------------------

    @classmethod
    def from_json(cls, path: str | Path, fallback_px_per_mm: float = 10.0) -> "CalibrationModel":
        """Load calibration from a JSON file.

        Falls back to *fallback_px_per_mm* if the file is missing or
        ``px_per_mm`` is not defined.
        """
        path = Path(path)
        if not path.exists():
            logger.warning("Calibration file not found: %s — using fallback %.2f px/mm", path, fallback_px_per_mm)
            return cls(
                px_per_mm=fallback_px_per_mm,
                track_centre_x_px=960,
                image_width_px=1920,
                image_height_px=1080,
            )

        with path.open(encoding="utf-8") as f:
            data = json.load(f)

        px_per_mm = float(data.get("px_per_mm", fallback_px_per_mm))
        track_centre_x = int(data.get("track_centre_x_px", data.get("image_width_px", 1920) // 2))
        width = int(data.get("image_width_px", 1920))
        height = int(data.get("image_height_px", 1080))

        dist_cfg = data.get("distortion", {})
        use_undistort = bool(dist_cfg.get("use_undistort", False))
        camera_matrix = None
        dist_coeffs = None

        if use_undistort:
            try:
                camera_matrix = np.array([
                    [dist_cfg["fx"], 0,              dist_cfg["cx"]],
                    [0,              dist_cfg["fy"],  dist_cfg["cy"]],
                    [0,              0,               1.0           ],
                ], dtype=np.float64)
                dist_coeffs = np.array(
                    [dist_cfg["k1"], dist_cfg["k2"], dist_cfg["p1"], dist_cfg["p2"], dist_cfg["k3"]],
                    dtype=np.float64,
                )
            except KeyError as exc:
                raise CalibrationError(f"Missing distortion key in calibration JSON: {exc}") from exc

        logger.info("Calibration loaded: %.2f px/mm, centre_x=%d", px_per_mm, track_centre_x)
        return cls(
            px_per_mm=px_per_mm,
            track_centre_x_px=track_centre_x,
            image_width_px=width,
            image_height_px=height,
            use_undistort=use_undistort,
            camera_matrix=camera_matrix,
            dist_coeffs=dist_coeffs,
        )

    def save_to_json(self, path: str | Path) -> None:
        """Persist current calibration to JSON."""
        path = Path(path)
        data = {
            "px_per_mm": self.px_per_mm,
            "track_centre_x_px": self.track_centre_x_px,
            "image_width_px": self.image_width_px,
            "image_height_px": self.image_height_px,
            "distortion": {
                "use_undistort": self.use_undistort,
            },
        }
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Calibration saved to %s", path)

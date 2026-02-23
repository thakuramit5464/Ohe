"""
processing/preprocess.py
------------------------
Pre-processing stage: converts a RawFrame into a ProcessedFrame.

Steps applied (in order):
1. ROI crop (optional)
2. Convert to grayscale
3. Lens undistortion (optional, if calibration says so)
4. CLAHE contrast enhancement
5. Gaussian blur (noise reduction)
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np

from ohe.core.config import ProcessingConfig, CalibrationConfig
from ohe.core.models import ProcessedFrame, RawFrame
from ohe.processing.calibration import CalibrationModel

logger = logging.getLogger(__name__)


class PreProcessor:
    """Transforms a :class:`RawFrame` into a :class:`ProcessedFrame`."""

    def __init__(
        self,
        config: ProcessingConfig,
        calibration: Optional[CalibrationModel] = None,
    ) -> None:
        self._cfg = config
        self._calibration = calibration

        # Build CLAHE object once
        self._clahe = cv2.createCLAHE(
            clipLimit=config.clahe_clip_limit,
            tileGridSize=tuple(config.clahe_tile_grid_size),  # type: ignore[arg-type]
        )

        # Parse ROI
        self._roi: Optional[Tuple[int, int, int, int]] = (
            tuple(config.roi) if config.roi and len(config.roi) == 4 else None  # type: ignore[assignment]
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, raw: RawFrame) -> ProcessedFrame:
        """Apply full pre-processing pipeline to *raw*.

        Returns:
            :class:`ProcessedFrame` with ROI cropped and enhanced grayscale image.
        """
        image = raw.image.copy()
        roi_x, roi_y = 0, 0

        # Step 1: ROI crop
        if self._roi:
            rx, ry, rw, rh = self._roi
            # Clamp to image bounds
            h, w = image.shape[:2]
            rx = max(0, min(rx, w - 1))
            ry = max(0, min(ry, h - 1))
            rw = min(rw, w - rx)
            rh = min(rh, h - ry)
            image = image[ry : ry + rh, rx : rx + rw]
            roi_x, roi_y = rx, ry

        # Step 2: Grayscale
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image

        # Step 3: Lens undistortion (skipped if no calibration or disabled)
        if self._calibration and self._calibration.use_undistort:
            gray = self._calibration.undistort(gray)

        # Step 4: CLAHE contrast enhancement
        enhanced = self._clahe.apply(gray)

        # Step 5: Gaussian blur
        k = self._cfg.blur_kernel_size
        blurred = cv2.GaussianBlur(enhanced, (k, k), 0)

        return ProcessedFrame(
            raw=raw,
            roi_image=blurred,
            roi_offset_x=roi_x,
            roi_offset_y=roi_y,
        )

    def set_roi(self, roi: Optional[Tuple[int, int, int, int]]) -> None:
        """Update the ROI at runtime (e.g. from UI drag)."""
        self._roi = roi

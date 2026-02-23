"""tests/unit/test_preprocess.py — PreProcessor unit tests using synthetic frames."""

import numpy as np
import pytest

from ohe.core.config import ProcessingConfig
from ohe.core.models import ProcessedFrame, RawFrame
from ohe.processing.preprocess import PreProcessor


def make_bgr_frame(h=200, w=400, frame_id=0) -> RawFrame:
    img = np.random.randint(0, 256, (h, w, 3), dtype=np.uint8)
    return RawFrame(frame_id=frame_id, timestamp_ms=0.0, image=img)


class TestPreProcessor:
    def test_output_is_grayscale(self):
        cfg = ProcessingConfig()
        pp = PreProcessor(cfg)
        pf = pp.run(make_bgr_frame())
        assert pf.roi_image.ndim == 2, "Output must be grayscale (2D)"

    def test_output_dtype_uint8(self):
        pp = PreProcessor(ProcessingConfig())
        pf = pp.run(make_bgr_frame())
        assert pf.roi_image.dtype == np.uint8

    def test_roi_crop_reduces_size(self):
        cfg = ProcessingConfig(roi=[50, 50, 100, 80])
        pp = PreProcessor(cfg)
        pf = pp.run(make_bgr_frame(h=200, w=400))
        h, w = pf.roi_image.shape
        assert h == 80
        assert w == 100

    def test_roi_offset_stored(self):
        cfg = ProcessingConfig(roi=[30, 20, 100, 80])
        pp = PreProcessor(cfg)
        pf = pp.run(make_bgr_frame())
        assert pf.roi_offset_x == 30
        assert pf.roi_offset_y == 20

    def test_no_roi_uses_full_frame(self):
        cfg = ProcessingConfig(roi=None)
        pp = PreProcessor(cfg)
        raw = make_bgr_frame(h=100, w=200)
        pf = pp.run(raw)
        assert pf.roi_image.shape == (100, 200)

    def test_raw_frame_preserved(self):
        pp = PreProcessor(ProcessingConfig())
        raw = make_bgr_frame(frame_id=42)
        pf = pp.run(raw)
        assert pf.raw.frame_id == 42

    def test_set_roi_updates_at_runtime(self):
        pp = PreProcessor(ProcessingConfig(roi=None))
        pp.set_roi((10, 10, 50, 50))
        raw = make_bgr_frame(h=200, w=200)
        pf = pp.run(raw)
        assert pf.roi_image.shape == (50, 50)

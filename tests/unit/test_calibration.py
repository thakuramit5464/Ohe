"""tests/unit/test_calibration.py — CalibrationModel unit tests."""

import json
import pytest
import numpy as np

from ohe.processing.calibration import CalibrationModel
from ohe.core.exceptions import CalibrationError


class TestCalibrationModel:
    def test_px_to_mm(self):
        cal = CalibrationModel(px_per_mm=10.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)
        assert cal.px_to_mm(100) == pytest.approx(10.0)

    def test_mm_to_px(self):
        cal = CalibrationModel(px_per_mm=10.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)
        assert cal.mm_to_px(15.0) == pytest.approx(150.0)

    def test_stagger_right(self):
        cal = CalibrationModel(px_per_mm=10.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)
        # Wire is 100px to the right → +10 mm
        assert cal.stagger_from_centre_px(600) == pytest.approx(10.0)

    def test_stagger_left(self):
        cal = CalibrationModel(px_per_mm=10.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)
        assert cal.stagger_from_centre_px(400) == pytest.approx(-10.0)

    def test_stagger_at_centre(self):
        cal = CalibrationModel(px_per_mm=10.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)
        assert cal.stagger_from_centre_px(500) == pytest.approx(0.0)

    def test_invalid_px_per_mm_raises(self):
        with pytest.raises(CalibrationError):
            CalibrationModel(px_per_mm=-1.0, track_centre_x_px=500, image_width_px=1000, image_height_px=500)

    def test_from_json_missing_file_uses_fallback(self, tmp_path):
        cal = CalibrationModel.from_json(tmp_path / "missing.json", fallback_px_per_mm=5.0)
        assert cal.px_per_mm == pytest.approx(5.0)

    def test_from_json_loads_correctly(self, tmp_path):
        data = {"px_per_mm": 8.5, "track_centre_x_px": 640, "image_width_px": 1280, "image_height_px": 720}
        p = tmp_path / "cal.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cal = CalibrationModel.from_json(p)
        assert cal.px_per_mm == pytest.approx(8.5)
        assert cal.track_centre_x_px == 640

    def test_save_and_reload(self, tmp_path):
        cal = CalibrationModel(px_per_mm=12.0, track_centre_x_px=960, image_width_px=1920, image_height_px=1080)
        p = tmp_path / "saved.json"
        cal.save_to_json(p)
        cal2 = CalibrationModel.from_json(p)
        assert cal2.px_per_mm == pytest.approx(12.0)

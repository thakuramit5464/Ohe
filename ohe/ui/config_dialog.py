"""
ui/config_dialog.py
--------------------
Modal settings dialog — lets the user tune detection parameters at runtime
without editing YAML manually.

Sections
--------
 • ROI (x, y, width, height or "full frame")
 • Preprocessing (CLAHE, blur)
 • Detection (Canny thresholds, Hough params, min confidence)
 • Rules / Thresholds (stagger warning/critical, diameter low/high)

Changes are applied to the in-memory config and optionally saved back to
config/default.yaml.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ohe.core.config import AppConfig
from ohe.ui.widgets import Palette


class ConfigDialog(QDialog):
    """Settings dialog — edit detection and rules parameters."""

    def __init__(self, cfg: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("OHE Settings")
        self.setMinimumSize(480, 520)
        self.setStyleSheet(f"background-color: {Palette.BG_DARK}; color: {Palette.TEXT};")
        self._cfg = cfg

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        tabs = QTabWidget()
        tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid #2a4a7f; }}
            QTabBar::tab {{ background: {Palette.BG_PANEL}; color: {Palette.TEXT_DIM};
                            padding: 6px 16px; border-radius: 4px 4px 0 0; }}
            QTabBar::tab:selected {{ background: {Palette.BG_CARD}; color: {Palette.TEXT}; }}
        """)
        tabs.addTab(self._build_roi_tab(), "ROI")
        tabs.addTab(self._build_detection_tab(), "Detection")
        tabs.addTab(self._build_rules_tab(), "Rules / Thresholds")
        lay.addWidget(tabs)

        # Buttons
        bbox = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Apply
        )
        save_btn = bbox.button(QDialogButtonBox.StandardButton.Apply)
        save_btn.setText("Save to YAML")
        bbox.accepted.connect(self._on_ok)
        bbox.rejected.connect(self.reject)
        save_btn.clicked.connect(self._on_save)
        bbox.setStyleSheet(f"color: {Palette.TEXT};")
        lay.addWidget(bbox)

    # ------------------------------------------------------------------
    # Tab builders
    # ------------------------------------------------------------------

    def _build_roi_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        self._roi_enabled = QCheckBox("Use custom ROI (uncheck = full frame)")
        roi = self._cfg.processing.roi
        self._roi_enabled.setChecked(roi is not None)
        form.addRow(self._roi_enabled)

        self._roi_x = _spin(0, 4096, roi[0] if roi else 0)
        self._roi_y = _spin(0, 4096, roi[1] if roi else 0)
        self._roi_w = _spin(1, 4096, roi[2] if roi else 640)
        self._roi_h = _spin(1, 4096, roi[3] if roi else 360)

        form.addRow("X (left edge, px):", self._roi_x)
        form.addRow("Y (top edge, px):", self._roi_y)
        form.addRow("Width (px):", self._roi_w)
        form.addRow("Height (px):", self._roi_h)

        note = QLabel(
            "Tip: For 640×360 video exclude text overlay at top (~70px)\n"
            "and pantograph structure below y=230.\n"
            "Default: [0, 70, 640, 160]"
        )
        note.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 11px;")
        form.addRow(note)
        return w

    def _build_detection_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        p = self._cfg.processing
        self._canny1 = _spin(1, 500, p.canny_threshold1)
        self._canny2 = _spin(1, 500, p.canny_threshold2)
        self._hough_thr = _spin(1, 500, p.hough_threshold)
        self._hough_min = _spin(1, 500, p.hough_min_line_length)
        self._hough_gap = _spin(0, 200, p.hough_max_line_gap)
        self._min_conf  = _dspin(0.0, 1.0, p.min_detection_confidence, step=0.05)
        self._clahe_clip = _dspin(0.5, 20.0, p.clahe_clip_limit, step=0.5)
        self._blur_k = _spin(1, 31, p.blur_kernel_size)

        form.addRow("Canny threshold 1:", self._canny1)
        form.addRow("Canny threshold 2:", self._canny2)
        form.addRow("Hough vote threshold:", self._hough_thr)
        form.addRow("Hough min line length (px):", self._hough_min)
        form.addRow("Hough max gap (px):", self._hough_gap)
        form.addRow("Min detection confidence:", self._min_conf)
        form.addRow("─" * 30, QLabel(""))
        form.addRow("CLAHE clip limit:", self._clahe_clip)
        form.addRow("Blur kernel size (odd):", self._blur_k)

        note = QLabel("Canny2 should be ~3× Canny1.\nLower Hough threshold = more lines (may add noise).")
        note.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 11px;")
        form.addRow(note)
        return w

    def _build_rules_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(10)

        r = self._cfg.rules
        self._s_warn  = _dspin(0, 300, r.stagger_warning_mm, step=5)
        self._s_crit  = _dspin(0, 500, r.stagger_critical_mm, step=5)
        self._d_lo_w  = _dspin(0, 30, r.diameter_low_warning_mm, step=0.5)
        self._d_lo_c  = _dspin(0, 30, r.diameter_low_critical_mm, step=0.5)
        self._d_hi_w  = _dspin(0, 50, r.diameter_high_warning_mm, step=0.5)
        self._d_hi_c  = _dspin(0, 50, r.diameter_high_critical_mm, step=0.5)

        form.addRow("── Stagger ──", QLabel(""))
        form.addRow("Warning |stagger| ≥ (mm):", self._s_warn)
        form.addRow("Critical |stagger| ≥ (mm):", self._s_crit)
        form.addRow("── Diameter ──", QLabel(""))
        form.addRow("Low warning < (mm):", self._d_lo_w)
        form.addRow("Low critical < (mm):", self._d_lo_c)
        form.addRow("High warning > (mm):", self._d_hi_w)
        form.addRow("High critical > (mm):", self._d_hi_c)
        return w

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _apply_to_config(self) -> None:
        """Write UI values back to the in-memory AppConfig."""
        p = self._cfg.processing
        if self._roi_enabled.isChecked():
            p.roi = [self._roi_x.value(), self._roi_y.value(),
                     self._roi_w.value(), self._roi_h.value()]
        else:
            p.roi = None

        p.canny_threshold1      = self._canny1.value()
        p.canny_threshold2      = self._canny2.value()
        p.hough_threshold       = self._hough_thr.value()
        p.hough_min_line_length = self._hough_min.value()
        p.hough_max_line_gap    = self._hough_gap.value()
        p.min_detection_confidence = self._min_conf.value()
        p.clahe_clip_limit      = self._clahe_clip.value()
        p.blur_kernel_size      = self._blur_k.value()

        r = self._cfg.rules
        r.stagger_warning_mm       = self._s_warn.value()
        r.stagger_critical_mm      = self._s_crit.value()
        r.diameter_low_warning_mm  = self._d_lo_w.value()
        r.diameter_low_critical_mm = self._d_lo_c.value()
        r.diameter_high_warning_mm = self._d_hi_w.value()
        r.diameter_high_critical_mm= self._d_hi_c.value()

    def _on_ok(self) -> None:
        self._apply_to_config()
        self.accept()

    def _on_save(self) -> None:
        self._apply_to_config()
        try:
            cfg_path = Path("config/default.yaml")
            with open(cfg_path, encoding="utf-8") as f:
                data = yaml.safe_load(f)

            p = self._cfg.processing
            data["processing"].update({
                "roi": p.roi,
                "canny_threshold1": p.canny_threshold1,
                "canny_threshold2": p.canny_threshold2,
                "hough_threshold": p.hough_threshold,
                "hough_min_line_length": p.hough_min_line_length,
                "hough_max_line_gap": p.hough_max_line_gap,
                "min_detection_confidence": p.min_detection_confidence,
                "clahe_clip_limit": p.clahe_clip_limit,
                "blur_kernel_size": p.blur_kernel_size,
            })
            r = self._cfg.rules
            data["rules"].update({
                "stagger_warning_mm": r.stagger_warning_mm,
                "stagger_critical_mm": r.stagger_critical_mm,
                "diameter_low_warning_mm": r.diameter_low_warning_mm,
                "diameter_low_critical_mm": r.diameter_low_critical_mm,
                "diameter_high_warning_mm": r.diameter_high_warning_mm,
                "diameter_high_critical_mm": r.diameter_high_critical_mm,
            })
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)
            QMessageBox.information(self, "Saved", f"Config saved to {cfg_path.resolve()}")
        except Exception as e:
            QMessageBox.critical(self, "Save Failed", str(e))


# ---------------------------------------------------------------------------
# Helper spin-box factories
# ---------------------------------------------------------------------------

def _spin(lo: int, hi: int, val: int) -> QSpinBox:
    sb = QSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setStyleSheet(f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; padding: 2px 4px;")
    return sb


def _dspin(lo: float, hi: float, val: float, step: float = 0.1) -> QDoubleSpinBox:
    sb = QDoubleSpinBox()
    sb.setRange(lo, hi)
    sb.setValue(val)
    sb.setSingleStep(step)
    sb.setDecimals(2)
    sb.setStyleSheet(f"background-color: {Palette.BG_CARD}; color: {Palette.TEXT}; padding: 2px 4px;")
    return sb

"""
ui/plot_panel.py
-----------------
Scrolling real-time plots for Stagger and Diameter using pyqtgraph.

Two vertically stacked plots:
  • Top:    Stagger (mm) — with ±150mm warning/critical bands
  • Bottom: Diameter (mm) — with wear threshold bands
"""

from __future__ import annotations

from PyQt6.QtWidgets import QVBoxLayout, QWidget
import pyqtgraph as pg

from ohe.core.models import Measurement
from ohe.ui.widgets import Palette

# Number of data points to keep in the scrolling window
_WINDOW = 300


class PlotPanel(QWidget):
    """Live scrolling plot panel for stagger and wire diameter."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        # pyqtgraph global dark background
        pg.setConfigOption("background", Palette.PLOT_BG)
        pg.setConfigOption("foreground", Palette.TEXT)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(4)

        self._win = pg.GraphicsLayoutWidget()
        self._win.setBackground(Palette.PLOT_BG)
        lay.addWidget(self._win)

        # --- Stagger plot ---
        self._p_stagger = self._win.addPlot(title="<b>Stagger (mm)</b>", row=0, col=0)
        self._setup_plot(self._p_stagger, "Stagger", "mm")
        self._add_threshold_band(self._p_stagger, -150, -200, Palette.CRITICAL, alpha=40)
        self._add_threshold_band(self._p_stagger,  150,  200, Palette.CRITICAL, alpha=40)
        self._add_threshold_band(self._p_stagger, -100, -150, Palette.WARNING, alpha=30)
        self._add_threshold_band(self._p_stagger,  100,  150, Palette.WARNING, alpha=30)
        self._add_hline(self._p_stagger, 0, Palette.TEXT_DIM, style=pg.QtCore.Qt.PenStyle.DashLine)

        self._stagger_curve = self._p_stagger.plot(pen=pg.mkPen(Palette.ACCENT, width=2))
        self._stagger_data: list[float] = []

        # --- Diameter plot ---
        self._p_diam = self._win.addPlot(title="<b>Wire Diameter (mm)</b>", row=1, col=0)
        self._setup_plot(self._p_diam, "Diameter", "mm")
        self._add_threshold_band(self._p_diam, 0,  8, Palette.CRITICAL, alpha=40)
        self._add_threshold_band(self._p_diam, 8, 10, Palette.WARNING, alpha=30)
        self._add_hline(self._p_diam, 12, Palette.OK)   # nominal

        self._diam_curve = self._p_diam.plot(pen=pg.mkPen("#00d4ff", width=2))
        self._diam_data:  list[float] = []

        # Link x axes
        self._p_diam.setXLink(self._p_stagger)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_measurement(self, m: Measurement) -> None:
        """Append a measurement point to both plots."""
        if m.stagger_mm is not None:
            self._stagger_data.append(m.stagger_mm)
            if len(self._stagger_data) > _WINDOW:
                self._stagger_data.pop(0)
            self._stagger_curve.setData(self._stagger_data)

        if m.diameter_mm is not None:
            self._diam_data.append(m.diameter_mm)
            if len(self._diam_data) > _WINDOW:
                self._diam_data.pop(0)
            self._diam_curve.setData(self._diam_data)

    def clear(self) -> None:
        self._stagger_data.clear()
        self._diam_data.clear()
        self._stagger_curve.setData([])
        self._diam_curve.setData([])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _setup_plot(plot: pg.PlotItem, label: str, units: str) -> None:
        plot.setLabel("left", label, units=units)
        plot.setLabel("bottom", "Frame index")
        plot.showGrid(x=True, y=True, alpha=0.15)
        plot.getAxis("left").setTextPen(Palette.TEXT)
        plot.getAxis("bottom").setTextPen(Palette.TEXT)

    @staticmethod
    def _add_threshold_band(plot, y_lo, y_hi, colour, alpha=40):
        brush = pg.mkBrush(colour + f"{alpha:02x}" if not colour.startswith("rgba") else colour)
        fill = pg.FillBetweenItem(
            pg.PlotDataItem([0, _WINDOW], [y_lo, y_lo]),
            pg.PlotDataItem([0, _WINDOW], [y_hi, y_hi]),
            brush=brush,
        )
        plot.addItem(fill)

    @staticmethod
    def _add_hline(plot, y, colour, style=pg.QtCore.Qt.PenStyle.SolidLine):
        line = pg.InfiniteLine(
            pos=y, angle=0,
            pen=pg.mkPen(colour, width=1, style=style),
        )
        plot.addItem(line)

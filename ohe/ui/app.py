"""
ui/app.py
----------
QApplication entry point.

Launch with:
    ohe-gui                         # installed entrypoint
    python -m ohe.ui.app            # direct module run
    python -m ohe.ui.app --video path/to/video.mp4
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from ohe.ui.main_window import MainWindow
from ohe.ui.widgets import GLOBAL_STYLESHEET


def run(argv: list[str] | None = None) -> int:
    """Create and launch the Qt application. Returns the exit code."""
    if argv is None:
        argv = sys.argv

    # High-DPI support
    app = QApplication(argv)
    app.setApplicationName("OHE Measurement System")
    app.setOrganizationName("OHE")
    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = MainWindow()
    window.show()

    # Auto-load video if passed as argument
    for arg in argv[1:]:
        if not arg.startswith("-"):
            import pathlib
            if pathlib.Path(arg).exists():
                window._video_path = arg
                from pathlib import Path
                window._lbl_file.setText(Path(arg).name)
                window._act_start.setEnabled(True)
                window._video_panel.show_placeholder(f"Ready: {Path(arg).name}")
            break

    return app.exec()


if __name__ == "__main__":
    sys.exit(run())

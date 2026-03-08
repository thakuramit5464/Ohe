"""
ui/share_dialog.py
-------------------
ShareDialog — export / share session data from the GUI.

Three modes:
  1. Save to folder — copies CSVs, JSONs, and event clips to a chosen directory.
  2. Export ZIP     — zips all session artefacts into a single archive.
  3. Email          — opens system email client via mailto: URI with pre-filled subject.
"""

from __future__ import annotations

import shutil
import zipfile
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from ohe.ui.widgets import Palette

logger = logging.getLogger(__name__)


class ShareDialog(QDialog):
    """
    Export / share session data dialog.

    Parameters
    ----------
    session_dir:  Path to the session output directory (contains .sqlite, .csv, .json).
    events_dir:   Path to the events directory (contains .mp4 clips).
    session_id:   Session identifier string for file naming.
    """

    def __init__(
        self,
        session_dir: Path,
        events_dir: Path,
        session_id: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._session_dir = session_dir
        self._events_dir  = events_dir
        self._session_id  = session_id

        self.setWindowTitle("Share / Export Session Data")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"background-color: {Palette.BG}; color: {Palette.TEXT};")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # Title
        title = QLabel("Export Session Data")
        title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Palette.TEXT};")
        layout.addWidget(title)

        sub = QLabel("Choose how to share the events, logs, and video clips.")
        sub.setStyleSheet(f"color: {Palette.TEXT_DIM}; font-size: 11px;")
        layout.addWidget(sub)

        # Export mode selection
        mode_box = QGroupBox("Export Mode")
        mode_box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid #2a4a7f; border-radius: 5px; color: {Palette.TEXT_DIM}; "
            f"margin-top: 8px; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
        )
        mode_lay = QVBoxLayout(mode_box)

        self._rb_folder = QRadioButton("Save to folder")
        self._rb_zip    = QRadioButton("Export as ZIP archive")
        self._rb_email  = QRadioButton("Send via Email (mailto)")
        self._rb_folder.setChecked(True)
        for rb in (self._rb_folder, self._rb_zip, self._rb_email):
            rb.setStyleSheet(f"color: {Palette.TEXT};")
            mode_lay.addWidget(rb)
        layout.addWidget(mode_box)

        # Content checkboxes
        content_box = QGroupBox("Include")
        content_box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid #2a4a7f; border-radius: 5px; color: {Palette.TEXT_DIM}; "
            f"margin-top: 8px; }} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; }}"
        )
        content_lay = QVBoxLayout(content_box)
        self._chk_logs   = QCheckBox("Event logs (CSV, JSON)")
        self._chk_clips  = QCheckBox("Event video clips (MP4)")
        self._chk_db     = QCheckBox("Session database (SQLite)")
        for chk in (self._chk_logs, self._chk_clips, self._chk_db):
            chk.setChecked(True)
            chk.setStyleSheet(f"color: {Palette.TEXT};")
            content_lay.addWidget(chk)
        layout.addWidget(content_box)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {Palette.BG_PANEL};
                border: 1px solid #2a4a7f;
                border-radius: 4px;
                text-align: center;
                color: {Palette.TEXT};
            }}
            QProgressBar::chunk {{ background-color: #4a8adf; border-radius: 4px; }}
            """
        )
        layout.addWidget(self._progress)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_export = QPushButton("Export")
        self._btn_cancel = QPushButton("Cancel")
        for btn in (self._btn_export, self._btn_cancel):
            btn.setFont(QFont("Segoe UI", 10))
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: {Palette.BG_CARD};
                    color: {Palette.TEXT};
                    border: 1px solid #2a4a7f;
                    border-radius: 5px;
                    padding: 6px 20px;
                }}
                QPushButton:hover {{ background-color: #2a4a7f; }}
                """
            )
        self._btn_export.clicked.connect(self._on_export)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_export)
        btn_row.addWidget(self._btn_cancel)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Export logic
    # ------------------------------------------------------------------

    def _on_export(self) -> None:
        if self._rb_folder.isChecked():
            self._export_to_folder()
        elif self._rb_zip.isChecked():
            self._export_zip()
        else:
            self._open_email()

    def _collect_files(self) -> list[Path]:
        """Gather all files that should be exported based on checkboxes."""
        files: list[Path] = []
        if self._chk_logs.isChecked():
            files.extend(self._session_dir.glob("*.csv"))
            files.extend(self._session_dir.glob("*.json"))
        if self._chk_db.isChecked():
            files.extend(self._session_dir.glob("*.sqlite"))
        if self._chk_clips.isChecked() and self._events_dir.exists():
            files.extend(self._events_dir.glob("*.mp4"))
        return files

    def _export_to_folder(self) -> None:
        dest = QFileDialog.getExistingDirectory(self, "Choose destination folder")
        if not dest:
            return
        dest_path = Path(dest)
        files = self._collect_files()
        if not files:
            QMessageBox.information(self, "Nothing to Export", "No session files found.")
            return
        self._progress.setVisible(True)
        self._progress.setRange(0, len(files))
        copied = 0
        for i, f in enumerate(files):
            try:
                shutil.copy2(f, dest_path / f.name)
                copied += 1
            except Exception as e:
                logger.warning("Could not copy %s: %s", f, e)
            self._progress.setValue(i + 1)
        self._progress.setVisible(False)
        QMessageBox.information(
            self, "Export Complete",
            f"Copied {copied} file(s) to:\n{dest_path}",
        )
        self.accept()

    def _export_zip(self) -> None:
        sid = self._session_id or "session"
        default_name = str(Path.home() / "Desktop" / f"{sid}_export.zip")
        zip_path, _ = QFileDialog.getSaveFileName(
            self, "Save ZIP archive", default_name, "ZIP Archives (*.zip)"
        )
        if not zip_path:
            return
        files = self._collect_files()
        if not files:
            QMessageBox.information(self, "Nothing to Export", "No session files found.")
            return
        self._progress.setVisible(True)
        self._progress.setRange(0, len(files))
        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for i, f in enumerate(files):
                    zf.write(f, arcname=f.name)
                    self._progress.setValue(i + 1)
        except Exception as e:
            QMessageBox.critical(self, "ZIP Export Failed", str(e))
            self._progress.setVisible(False)
            return
        self._progress.setVisible(False)
        QMessageBox.information(
            self, "ZIP Created",
            f"Archive saved to:\n{zip_path}\n\n{len(files)} file(s) included.",
        )
        self.accept()

    def _open_email(self) -> None:
        sid = self._session_id or "OHE session"
        clip_count = len(list(self._events_dir.glob("*.mp4"))) if self._events_dir.exists() else 0
        subject = f"OHE Inspection Report — {sid}"
        body = (
            f"Please find attached the OHE inspection session report.%0A"
            f"Session ID: {sid}%0A"
            f"Event clips: {clip_count}%0A"
            f"%0A(Attach exported files manually)"
        )
        mailto = f"mailto:?subject={subject}&body={body}"
        QDesktopServices.openUrl(QUrl(mailto))
        self.accept()

"""
ui/share_dialog.py
-------------------
ShareDialog — export / share session data from the GUI.

Three modes:
  1. Save to folder — copies CSVs, JSONs, and event clips to a chosen directory.
  2. Export ZIP     — zips all session artefacts into one archive.
  3. Email          — opens the system email client via mailto: URI.

Default export location: ~/Documents  (Windows: C:\\Users\\<name>\\Documents)
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
    QFrame,
)

from ohe.ui.widgets import Palette

logger = logging.getLogger(__name__)

_DOCS_DIR = Path.home() / "Documents"


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
        self.setMinimumWidth(520)
        self.setMinimumHeight(440)
        self.setStyleSheet(
            f"background-color: {Palette.BG_DARK}; color: {Palette.TEXT};"
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Header ──────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        icon_lbl = QLabel("📤")
        icon_lbl.setFont(QFont("Segoe UI", 18))
        icon_lbl.setStyleSheet("background: transparent;")
        header_row.addWidget(icon_lbl)

        title_col = QVBoxLayout()
        title = QLabel("Export Session Data")
        title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {Palette.TEXT}; background: transparent;")
        sub = QLabel("Choose how to share events, logs, and video clips.")
        sub.setStyleSheet(
            f"color: {Palette.TEXT_DIM}; font-size: 11px; background: transparent;"
        )
        title_col.addWidget(title)
        title_col.addWidget(sub)

        header_row.addLayout(title_col)
        header_row.addStretch()
        layout.addLayout(header_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"color: {Palette.BORDER};")
        layout.addWidget(div)

        # ── Export Mode ──────────────────────────────────────────────────────
        mode_box = self._make_group("Export Mode")
        mode_lay = QVBoxLayout(mode_box)
        mode_lay.setSpacing(8)

        self._rb_folder = QRadioButton("📁  Save to folder")
        self._rb_zip    = QRadioButton("🗜  Export as ZIP archive")
        self._rb_email  = QRadioButton("✉  Send via Email (mailto)")
        self._rb_folder.setChecked(True)

        for rb in (self._rb_folder, self._rb_zip, self._rb_email):
            rb.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
            mode_lay.addWidget(rb)

        # Live path preview label
        self._path_preview = QLabel()
        self._path_preview.setWordWrap(True)
        self._path_preview.setStyleSheet(
            f"color: {Palette.ACCENT2}; font-size: 10px; "
            f"padding: 6px 8px; border-radius: 4px; "
            f"background-color: {Palette.BG_PANEL};"
        )
        mode_lay.addWidget(self._path_preview)
        layout.addWidget(mode_box)

        # Connect radio buttons to update the preview
        self._rb_folder.toggled.connect(self._update_path_preview)
        self._rb_zip.toggled.connect(self._update_path_preview)
        self._rb_email.toggled.connect(self._update_path_preview)
        self._update_path_preview()   # populate on open

        # ── Content ──────────────────────────────────────────────────────────
        content_box = self._make_group("Include")
        content_lay = QVBoxLayout(content_box)
        content_lay.setSpacing(6)

        self._chk_logs  = QCheckBox("Event logs (CSV + JSON)")
        self._chk_clips = QCheckBox("Event video clips (MP4)")
        self._chk_db    = QCheckBox("Session database (SQLite)")
        for chk in (self._chk_logs, self._chk_clips, self._chk_db):
            chk.setChecked(True)
            chk.setStyleSheet(f"color: {Palette.TEXT}; font-size: 12px;")
            content_lay.addWidget(chk)
        layout.addWidget(content_box)

        # ── Progress bar ─────────────────────────────────────────────────────
        self._progress = QProgressBar()
        self._progress.setVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {Palette.BG_PANEL};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 {Palette.ACCENT2}, stop:1 #7b2fff);
                border-radius: 4px;
            }}
            """
        )
        layout.addWidget(self._progress)

        layout.addStretch()

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_div = QFrame()
        btn_div.setFrameShape(QFrame.Shape.HLine)
        btn_div.setStyleSheet(f"color: {Palette.BORDER};")
        layout.addWidget(btn_div)

        btn_row = QHBoxLayout()
        self._btn_export = QPushButton("Export")
        self._btn_cancel = QPushButton("Cancel")

        self._btn_export.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._btn_cancel.setFont(QFont("Segoe UI", 10))

        self._btn_export.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Palette.ACCENT2};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 28px;
                font-weight: 700;
            }}
            QPushButton:hover {{ background-color: #6aaaf7; }}
            QPushButton:pressed {{ background-color: #2a5aaf; }}
            """
        )
        self._btn_cancel.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {Palette.BG_CARD};
                color: {Palette.TEXT};
                border: 1px solid {Palette.BORDER};
                border-radius: 6px;
                padding: 8px 22px;
            }}
            QPushButton:hover {{ background-color: #1a4a80; border-color: {Palette.ACCENT2}; }}
            """
        )
        self._btn_export.clicked.connect(self._on_export)
        self._btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_export)
        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _make_group(title: str) -> QGroupBox:
        box = QGroupBox(title)
        box.setStyleSheet(
            f"QGroupBox {{ border: 1px solid {Palette.BORDER}; border-radius: 8px; "
            f"color: {Palette.TEXT_DIM}; margin-top: 10px; font-weight: 600; font-size: 11px; }}"
            f"QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 6px; }}"
        )
        return box

    def _update_path_preview(self) -> None:
        """Refresh the path hint label whenever the export mode changes."""
        sid = self._session_id or "session"
        if self._rb_folder.isChecked():
            text = f"📍  Default destination: {_DOCS_DIR}"
        elif self._rb_zip.isChecked():
            text = f"📍  Default save location: {_DOCS_DIR / f'{sid}_export.zip'}"
        else:
            text = "📧  Opens your default email client with a pre-filled message."
        self._path_preview.setText(text)

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
        default_docs = str(_DOCS_DIR)
        dest = QFileDialog.getExistingDirectory(
            self, "Choose destination folder", default_docs
        )
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
            f"✅  Copied {copied} file(s) to:\n{dest_path}",
        )
        self.accept()

    def _export_zip(self) -> None:
        sid = self._session_id or "session"
        default_name = str(_DOCS_DIR / f"{sid}_export.zip")
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
            f"✅  Archive saved to:\n{zip_path}\n\n{len(files)} file(s) included.",
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

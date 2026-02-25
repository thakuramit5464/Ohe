# OHE Stagger & Wire Diameter Measurement System

A production-ready Windows-based software for measuring **OHE contact wire stagger and diameter** from video using classical computer vision.

## Features

- 📹 Offline video processing (MP4/AVI/MKV)
- 📏 Real-time stagger (mm) and diameter (mm) measurement
- ⚠️  Configurable anomaly detection with WARNING/CRITICAL thresholds
- 📊 Live scrolling pyqtgraph plots (stagger + diameter traces with threshold bands)
- 🗃️  SQLite session logging + CSV/JSON export after every run
- 🖥️  PyQt6 GUI — video panel, metric cards, anomaly log, menu bar
- ⚙️  In-GUI settings dialog (ROI, Canny, Hough, rules) — no YAML editing needed
- 🎯  Calibration wizard — point-click any two reference points → compute px/mm
- ⌨️  Headless CLI (`ohe process`) with tqdm progress bar and auto-export

## Architecture

```
Video → Ingestion → PreProcess → Detect → Measure → Rules → DataBus → UI / Logs
           │            │          │         │          │
        VideoFile    ROI/CLAHE  Hough+    px→mm    Stagger/       SQLite
        Provider      /Blur    Gaussian  Calibr.   Diameter       + CSV
```

## Quick Start

### 1. Create & activate virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -e ".[dev]"
```

### 3. Run tests (76 tests)

```powershell
pytest tests/ -v
```

### 4. Launch the GUI

```powershell
ohe-gui                                               # blank start
ohe-gui data\sample_videos\overlap_first4s_looped.mp4 # auto-load video
```

### 5. Process headless (CLI)

```powershell
ohe process --video data\sample_videos\overlap_first4s_looped.mp4
ohe sessions          # list all saved sessions
ohe export --db data\sessions\<id>.sqlite   # re-export a session
```

### 6. Debug visualiser (parameter tuning)

```powershell
python tools/debug_visualiser.py --video data\sample_videos\overlap.mp4 --every 1
# outputs: data/debug/<timestamp>/annotated.mp4 + frame_XXXX.png + summary.csv
```

## Configuration

| File | Purpose |
|---|---|
| `config/default.yaml` | ROI, Canny/Hough params, rules thresholds, paths |
| `config/calibration.json` | px/mm scale factor per camera setup |

**In-GUI**: `Tools → Settings…` (Ctrl+,) opens the settings dialog.
**In-GUI**: `Tools → Calibration Wizard…` walks you through computing px/mm from a reference frame.

## Project Structure

```
ohe/
├── core/         # Models, config (Pydantic), DataBus, exceptions
├── ingestion/    # VideoFileProvider, CameraProvider (stub)
├── processing/   # PreProcess, WireDetector (Hough+Gaussian FWHM), Calibration, Pipeline
├── rules/        # Threshold config + RulesEngine (anomaly generation)
├── logging_/     # SessionLogger (SQLite), CsvWriter, LogWorker (thread), SessionExporter
└── ui/           # PyQt6: MainWindow, VideoPanel, PlotPanel, AnomalyPanel,
                  #        PipelineWorker (QThread), ConfigDialog, CalibrationWizard
tools/
└── debug_visualiser.py   # Annotated MP4 + PNG frames + CSV for parameter tuning
scripts/
├── build_exe.ps1        # PyInstaller bundle only
└── build_installer.ps1  # Full pipeline: tests → PyInstaller → Inno Setup
installer/
├── ohe_setup.iss        # Inno Setup 6 script
└── README.md            # Installer build guide
assets/
└── icon.ico             # App icon (replace placeholder)
```

## Build Standalone Executable

```powershell
# PyInstaller bundle only (no installer needed, just zip & share)
.\scripts\build_exe.ps1
# → dist\ohe-gui\ohe-gui.exe
```

## Build Windows Installer

Requires free [Inno Setup 6](https://jrsoftware.org/isinfo.php).

```powershell
# One command: runs tests → PyInstaller → compiles setup wizard
.\scripts\build_installer.ps1
# → installer\Output\OHE_Setup_1.0.0.exe
```

The installer gives end-users a **Next/Install/Finish** setup wizard,
Start Menu shortcut, optional Desktop shortcut, optional `.mp4` association,
and a clean uninstaller — **no Python required** on their machine.

See [`installer/README.md`](installer/README.md) for full details.

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Core foundation, ingestion, preprocessing | ✅ Complete |
| 2 | Detection & measurement engine, debug visualiser | ✅ Complete |
| 3 | Rules engine, threaded logging, CLI with progress bar | ✅ Complete |
| 4 | PyQt6 GUI shell (video panel, plots, anomaly log) | ✅ Complete |
| 5 | Settings dialog, calibration wizard, PyInstaller packaging | ✅ Complete |
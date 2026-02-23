# OHE Stagger & Wire Diameter Measurement System

A production-ready Windows-based software for measuring **OHE contact wire stagger and diameter** from video using classical computer vision.

## Features

- 📹 Offline video processing (file-based input)
- 📏 Real-time stagger (mm) and diameter (mm) measurement
- ⚠️ Configurable anomaly detection with thresholds
- 📊 Live charts (stagger / diameter over time)
- 🗃️ Session logging to SQLite + CSV export
- 🖥️ PyQt6 GUI with video overlay and alert panel
- ⌨️ Headless CLI mode for batch processing

## Architecture

```
Video → Ingestion → Pre-Process → Detect → Measure → Rules → DataBus → UI / Logs
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

### 3. Run tests

```powershell
pytest tests/ -v --cov=ohe
```

### 4. Process a video (CLI)

```powershell
ohe process --video data/sample_videos/test.mp4 --output data/sessions/out.csv
```

### 5. Launch GUI

```powershell
python -m ohe.ui.app
```

## Configuration

Edit `config/default.yaml` to adjust thresholds, ROI, and logging paths.  
Edit `config/calibration.json` to set pixel-per-mm scale factors per camera.

## Project Structure

```
ohe/
├── core/         # Models, config, DataBus, exceptions
├── ingestion/    # Frame providers (video file, camera stub)
├── processing/   # Pre-process, detect, measure, calibrate, pipeline
├── rules/        # Threshold config + anomaly engine
├── logging_/     # SQLite session, CSV writer, export
└── ui/           # PyQt6 GUI (main window + panels)
```

## Development Phases

| Phase | Scope | Status |
|-------|-------|--------|
| 1 | Core foundation, ingestion, preprocessing | ✅ In Progress |
| 2 | Detection & measurement engine | 🔲 Planned |
| 3 | Rules engine & logging | 🔲 Planned |
| 4 | PyQt6 UI | 🔲 Planned |
| 5 | Polish, config UI, packaging | 🔲 Planned |
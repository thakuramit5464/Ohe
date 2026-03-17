"""
core/config.py
--------------
Loads, validates, and exposes the application config from a YAML file.

Usage:
    from ohe.core.config import load_config, AppConfig
    cfg = load_config()            # loads config/default.yaml
    cfg = load_config("my.yaml")   # loads a custom file
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from ohe.core.exceptions import ConfigError

logger = logging.getLogger(__name__)


def _resolve_project_root() -> Path:
    """
    Return the application install directory (parent of the .exe).

    - Frozen (PyInstaller one-dir): directory that contains ohe-gui.exe
    - Normal Python run: two parents above this source file (project root)
    """
    import sys
    if getattr(sys, "frozen", False):
        # sys.executable is  <install_dir>/ohe-gui.exe
        return Path(sys.executable).resolve().parent
    # Dev / editable install: …/ohe/core/config.py  →  parents[2] is project root
    return Path(__file__).resolve().parents[2]


def _resolve_bundle_root() -> Path:
    """
    Return the directory where PyInstaller placed the bundled read-only data.

    - Frozen (PyInstaller COLLECT one-dir): sys._MEIPASS  →  <install_dir>/_internal/
    - Normal Python run: same as project root
    """
    import sys
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return _resolve_project_root()


_PROJECT_ROOT  = _resolve_project_root()
_BUNDLE_ROOT   = _resolve_bundle_root()   # where bundled datas (config/*.yaml) live
_DEFAULT_CONFIG = _BUNDLE_ROOT / "config" / "default.yaml"


# ---------------------------------------------------------------------------
# Pydantic sub-models
# ---------------------------------------------------------------------------

class IngestionConfig(BaseModel):
    target_fps: float = 0
    frame_skip: int = Field(1, ge=1)


class ProcessingConfig(BaseModel):
    roi: Optional[list[int]] = None  # [x, y, w, h]
    clahe_clip_limit: float = 2.0
    clahe_tile_grid_size: list[int] = [8, 8]
    blur_kernel_size: int = Field(5, ge=1)
    canny_threshold1: int = 50
    canny_threshold2: int = 150
    hough_rho: float = 1.0
    hough_theta_deg: float = 1.0
    hough_threshold: int = 80
    hough_min_line_length: int = 50
    hough_max_line_gap: int = 10
    min_detection_confidence: float = Field(0.5, ge=0.0, le=1.0)

    @field_validator("blur_kernel_size")
    @classmethod
    def must_be_odd(cls, v: int) -> int:
        if v % 2 == 0:
            raise ValueError("blur_kernel_size must be odd")
        return v


class CalibrationConfig(BaseModel):
    file: str = "config/calibration.json"
    fallback_px_per_mm: float = Field(10.0, gt=0)


class StaggerThreshold(BaseModel):
    warning_mm: float = 150.0
    critical_mm: float = 200.0


class DiameterThreshold(BaseModel):
    min_warning_mm: float = 10.0
    min_critical_mm: float = 8.0
    max_warning_mm: float = 15.0
    max_critical_mm: float = 17.0


class RulesConfig(BaseModel):
    stagger: StaggerThreshold = StaggerThreshold()
    diameter: DiameterThreshold = DiameterThreshold()


class LoggingConfig(BaseModel):
    session_dir: str = "data/sessions"
    sqlite_enabled: bool = True
    csv_enabled: bool = True
    csv_max_rows: int = Field(100_000, gt=0)
    log_level: str = "INFO"


class UIConfig(BaseModel):
    window_width: int = 1440
    window_height: int = 900
    chart_history_frames: int = 500
    overlay_wire_colour: list[int] = [0, 255, 0]
    overlay_centre_colour: list[int] = [0, 0, 255]


class InputConfig(BaseModel):
    """Input source configuration."""
    mode: str = "video_file"
    """'video_file' or 'camera'."""
    camera_index: int = 0
    """OpenCV camera index for live camera mode."""
    camera_fps: float = Field(25.0, gt=0)
    """Target FPS for camera capture (0 = native camera rate)."""


class SpeedConfig(BaseModel):
    """Vehicle speed source configuration."""
    mode: str = "simulated"
    """'simulated' or 'live'."""
    simulated_base_kmh: float = Field(60.0, ge=0)
    """Base speed for the SimulatedSpeedProvider."""
    simulated_jitter_kmh: float = Field(5.0, ge=0)
    """Maximum random jitter per frame (km/h)."""


class EventVideoConfig(BaseModel):
    """Controls event clip generation."""
    enabled: bool = True
    pre_frames: int = Field(90, ge=0)
    """Number of frames before the anomaly frame to include in the clip."""
    post_frames: int = Field(60, ge=0)
    """Number of frames after the anomaly frame to include in the clip."""
    events_dir: str = "data/events"
    """Directory where event MP4 clips are stored (used as fallback when no track name)."""
    video_fps: float = Field(25.0, gt=0)
    """Frame-rate used when encoding event clips."""


class GeoConfig(BaseModel):
    """Geolocation settings."""
    enabled: bool = True
    mode: str = "simulated"
    """'simulated' or 'live'."""
    simulated_speed_kmh: float = Field(60.0, ge=0)
    """Speed value used by the SimulatedGeoProvider (legacy — prefer speed.simulated_base_kmh)."""
    origin_latitude: float = 28.6139
    """Starting latitude for simulation (default: New Delhi, India)."""
    origin_longitude: float = 77.2090
    """Starting longitude for simulation."""


class VideoDirectoryConfig(BaseModel):
    """Paths for training video storage and frame extraction."""
    training_videos_dir: str = "data/videos"
    """Directory containing training / reference video files."""
    frames_dir: str = "data/frames"
    """Directory for extracted debug/training frames."""
    models_dir: str = "data/models"
    """Directory for saved model weights / calibration exports."""
    tracks_dir: str = "data/tracks"
    """Root directory for track-scoped test run data."""


class MastDetectionConfig(BaseModel):
    """Classical CV mast detection parameters."""
    enabled: bool = True
    """Toggle mast detection on/off."""

    # Vertical edge sensitivity
    sobel_ksize: int = Field(3, ge=1)
    """Kernel size for Sobel X operator."""
    edge_threshold: int = Field(80, ge=0, le=255)
    """Binary threshold applied after Sobel."""

    # Contour / shape filters
    min_contour_area: int = Field(500, ge=1)
    """Minimum bounding-box area (px^2) to consider a mast candidate."""
    min_aspect_ratio: float = Field(2.5, gt=0)
    """Minimum height/width ratio — masts are tall and narrow."""
    max_aspect_ratio: float = Field(30.0, gt=0)
    """Maximum height/width ratio — reject excessively thin artefacts."""

    # Lateral zone filter (fraction of frame width)
    side_zone_fraction: float = Field(0.35, gt=0, le=0.5)
    """Only accept masts within this fraction of left/right frame edge."""

    # Temporal consistency
    min_frames_to_confirm: int = Field(3, ge=1)
    """Number of consecutive frames a candidate must appear before confirmed."""
    iou_threshold: float = Field(0.25, ge=0.0, le=1.0)
    """Minimum IoU to match a candidate bbox across frames."""


class ChainageConfig(BaseModel):
    """Chainage (distance along track) estimation parameters."""
    speed_source: str = "config"
    """'config' — use simulated_speed_kmh, 'pipeline' — accept per-frame speed."""
    simulated_speed_kmh: float = Field(60.0, ge=0)
    """Constant speed used when speed_source == 'config'."""
    initial_chainage_m: float = 0.0
    """Starting chainage value for the session (metres)."""


class LaserHeightConfig(BaseModel):
    """Wire height measurement from laser sensor."""
    mode: str = "simulated"
    """'simulated' or 'real'. Real mode accepts distance from external sensor."""
    sensor_mount_height_m: float = Field(6.5, gt=0)
    """Height of the laser sensor above the rail head (metres)."""
    nominal_height_m: float = Field(5.25, gt=0)
    """Nominal wire height used in simulated mode (metres)."""
    noise_std_m: float = Field(0.015, ge=0)
    """Standard deviation of Gaussian noise added in simulated mode (metres)."""


# ---------------------------------------------------------------------------
# Root config model
# ---------------------------------------------------------------------------

class AppConfig(BaseModel):
    ingestion: IngestionConfig = IngestionConfig()
    processing: ProcessingConfig = ProcessingConfig()
    calibration: CalibrationConfig = CalibrationConfig()
    rules: RulesConfig = RulesConfig()
    logging: LoggingConfig = LoggingConfig()
    ui: UIConfig = UIConfig()
    input: InputConfig = InputConfig()
    speed: SpeedConfig = SpeedConfig()
    event_video: EventVideoConfig = EventVideoConfig()
    geo: GeoConfig = GeoConfig()
    video_directory: VideoDirectoryConfig = VideoDirectoryConfig()
    mast_detection: MastDetectionConfig = MastDetectionConfig()
    chainage: ChainageConfig = ChainageConfig()
    laser_height: LaserHeightConfig = LaserHeightConfig()
    model_version: str = "classical-v1"
    """Detection algorithm / model version string stored in every anomaly log."""

    # ------------------------------------------------------------------
    # Internal: path resolver
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_data_path(raw: str) -> Path:
        """
        Resolve a data path string to an absolute Path.

        Rules (in priority order):
        1. Already absolute  →  use as-is.
        2. Starts with ``~`` →  expand home directory (e.g. ``~/Documents/ohe``
                                  becomes ``C:\\Users\\<name>\\Documents\\ohe``).
        3. Relative           →  resolve relative to the project root (dev mode)
                                  or AppData\\Roaming\\OHE (frozen exe).
        """
        import sys
        p = Path(raw)
        if p.is_absolute():
            return p
        if raw.startswith("~"):
            return p.expanduser()
        # Relative path
        if getattr(sys, "frozen", False):
            return Path.home() / "AppData" / "Roaming" / "OHE" / raw
        return _PROJECT_ROOT / raw

    def events_dir_path(self) -> Path:
        """Resolve event clips directory (fallback when no track name)."""
        return self._resolve_data_path(self.event_video.events_dir)

    def track_dir_path(self, track_name: str) -> Path:
        """Return the root directory for a named track / test run.

        Structure::

            <tracks_dir>/<track_name>/
                events/
                logs/
                reports/
                videos/
        """
        base = self._resolve_data_path(self.video_directory.tracks_dir)
        return base / track_name

    def ensure_track_dirs(self, track_name: str) -> Path:
        """Create all sub-directories for a track and return the track root."""
        track_root = self.track_dir_path(track_name)
        for sub in ("events", "logs", "reports", "videos"):
            (track_root / sub).mkdir(parents=True, exist_ok=True)
        return track_root

    def ensure_data_dirs(self) -> None:
        """Create all base data directories if they don't exist."""
        dirs = [
            self._resolve_data_path(self.logging.session_dir),
            self.events_dir_path(),
            self._resolve_data_path(self.video_directory.training_videos_dir),
            self._resolve_data_path(self.video_directory.frames_dir),
            self._resolve_data_path(self.video_directory.models_dir),
            self._resolve_data_path(self.video_directory.tracks_dir),
        ]
        for d in dirs:
            try:
                Path(d).mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

    def calibration_path(self) -> Path:
        """Resolve calibration file path.

        - Frozen exe: writable copy in %APPDATA%\\OHE\\calibration.json
          (falls back to bundled read-only template if the user copy is absent).
        - Dev run  : relative to project root as before.
        """
        import sys
        p = Path(self.calibration.file)
        if p.is_absolute():
            return p
        if getattr(sys, "frozen", False):
            appdata = Path.home() / "AppData" / "Roaming" / "OHE"
            appdata.mkdir(parents=True, exist_ok=True)
            user_path = appdata / p.name
            if not user_path.exists():
                # Copy the bundled read-only template on first run
                bundled = _BUNDLE_ROOT / p
                if bundled.exists():
                    import shutil
                    shutil.copy2(bundled, user_path)
            return user_path
        return _PROJECT_ROOT / p

    def session_dir_path(self) -> Path:
        """Resolve session directory.

        - Frozen exe: %APPDATA%\\OHE\\sessions  (writable by standard users).
        - Dev run  : relative to project root as before.
        """
        import sys
        p = Path(self.logging.session_dir)
        if p.is_absolute():
            return p
        if getattr(sys, "frozen", False):
            sessions = Path.home() / "AppData" / "Roaming" / "OHE" / "sessions"
            sessions.mkdir(parents=True, exist_ok=True)
            return sessions
        return _PROJECT_ROOT / p


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------

def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate AppConfig from a YAML file.

    Args:
        path: Explicit path to a YAML file. Defaults to ``config/default.yaml``.

    Returns:
        Validated :class:`AppConfig` instance.

    Raises:
        ConfigError: If the file is missing or contains invalid values.
    """
    config_path = Path(path) if path else _DEFAULT_CONFIG

    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"YAML parse error in {config_path}: {exc}") from exc

    try:
        cfg = AppConfig.model_validate(raw)
    except Exception as exc:
        raise ConfigError(f"Invalid configuration values: {exc}") from exc

    logger.info("Configuration loaded from %s", config_path)
    return cfg

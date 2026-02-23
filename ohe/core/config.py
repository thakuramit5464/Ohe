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

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG = _PROJECT_ROOT / "config" / "default.yaml"


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

    def calibration_path(self) -> Path:
        """Resolve calibration file path relative to project root."""
        p = Path(self.calibration.file)
        return p if p.is_absolute() else _PROJECT_ROOT / p

    def session_dir_path(self) -> Path:
        """Resolve session directory relative to project root."""
        p = Path(self.logging.session_dir)
        return p if p.is_absolute() else _PROJECT_ROOT / p


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

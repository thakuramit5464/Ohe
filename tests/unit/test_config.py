"""tests/unit/test_config.py — Config loader tests."""

import pytest
from pathlib import Path

from ohe.core.config import load_config, AppConfig
from ohe.core.exceptions import ConfigError


def test_load_default_config():
    """Default config/default.yaml must load successfully."""
    cfg = load_config()
    assert isinstance(cfg, AppConfig)
    assert cfg.processing.blur_kernel_size % 2 == 1
    assert cfg.rules.stagger.critical_mm > cfg.rules.stagger.warning_mm
    assert cfg.rules.diameter.min_critical_mm < cfg.rules.diameter.min_warning_mm


def test_missing_file_raises_config_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_invalid_yaml_raises_config_error(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("processing:\n  blur_kernel_size: 4\n", encoding="utf-8")  # 4 is even → invalid
    with pytest.raises(ConfigError):
        load_config(bad)


def test_custom_overrides(tmp_path):
    yaml_content = """
rules:
  stagger:
    warning_mm: 100.0
    critical_mm: 180.0
"""
    p = tmp_path / "custom.yaml"
    p.write_text(yaml_content, encoding="utf-8")
    cfg = load_config(p)
    assert cfg.rules.stagger.warning_mm == 100.0
    assert cfg.rules.stagger.critical_mm == 180.0

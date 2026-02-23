"""
rules/thresholds.py
--------------------
Strongly-typed threshold objects populated from AppConfig.
"""

from __future__ import annotations

from dataclasses import dataclass

from ohe.core.config import RulesConfig


@dataclass(frozen=True)
class StaggerThresholds:
    warning_mm: float
    critical_mm: float


@dataclass(frozen=True)
class DiameterThresholds:
    min_warning_mm: float
    min_critical_mm: float
    max_warning_mm: float
    max_critical_mm: float


@dataclass(frozen=True)
class Thresholds:
    stagger: StaggerThresholds
    diameter: DiameterThresholds

    @classmethod
    def from_config(cls, cfg: RulesConfig) -> "Thresholds":
        return cls(
            stagger=StaggerThresholds(
                warning_mm=cfg.stagger.warning_mm,
                critical_mm=cfg.stagger.critical_mm,
            ),
            diameter=DiameterThresholds(
                min_warning_mm=cfg.diameter.min_warning_mm,
                min_critical_mm=cfg.diameter.min_critical_mm,
                max_warning_mm=cfg.diameter.max_warning_mm,
                max_critical_mm=cfg.diameter.max_critical_mm,
            ),
        )

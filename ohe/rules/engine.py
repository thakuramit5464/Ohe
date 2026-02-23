"""
rules/engine.py
---------------
RulesEngine: evaluates a Measurement against configured thresholds and
produces a list of Anomaly objects for any violations detected.

Anomaly types produced:
  * STAGGER_RIGHT  — wire too far right of track centre
  * STAGGER_LEFT   — wire too far left of track centre
  * DIAMETER_LOW   — wire diameter below minimum
  * DIAMETER_HIGH  — wire diameter above maximum

Severity levels:
  * WARNING  — threshold exceeded but within critical limit
  * CRITICAL — critical threshold exceeded
"""

from __future__ import annotations

import logging

from ohe.core.models import Anomaly, Measurement
from ohe.rules.thresholds import Thresholds

logger = logging.getLogger(__name__)


class RulesEngine:
    """Converts a :class:`Measurement` into zero or more :class:`Anomaly` objects."""

    def __init__(self, thresholds: Thresholds) -> None:
        self._t = thresholds

    def evaluate(self, m: Measurement) -> list[Anomaly]:
        """Evaluate *m* and return all threshold violations."""
        anomalies: list[Anomaly] = []

        if m.stagger_mm is not None:
            anomalies.extend(self._check_stagger(m))

        if m.diameter_mm is not None:
            anomalies.extend(self._check_diameter(m))

        if anomalies:
            logger.info(
                "Frame %d: %d anomaly(ies) detected: %s",
                m.frame_id,
                len(anomalies),
                [a.anomaly_type for a in anomalies],
            )

        return anomalies

    # ------------------------------------------------------------------
    # Private checks
    # ------------------------------------------------------------------

    def _check_stagger(self, m: Measurement) -> list[Anomaly]:
        results: list[Anomaly] = []
        val = m.stagger_mm  # type: ignore[assignment]
        t = self._t.stagger
        abs_val = abs(val)
        direction = "RIGHT" if val >= 0 else "LEFT"

        if abs_val >= t.critical_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type=f"STAGGER_{direction}",
                value=val,
                threshold=t.critical_mm if val >= 0 else -t.critical_mm,
                severity="CRITICAL",
                message=f"Stagger {direction}: {val:.1f} mm exceeds CRITICAL limit ±{t.critical_mm} mm",
            ))
        elif abs_val >= t.warning_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type=f"STAGGER_{direction}",
                value=val,
                threshold=t.warning_mm if val >= 0 else -t.warning_mm,
                severity="WARNING",
                message=f"Stagger {direction}: {val:.1f} mm exceeds WARNING limit ±{t.warning_mm} mm",
            ))
        return results

    def _check_diameter(self, m: Measurement) -> list[Anomaly]:
        results: list[Anomaly] = []
        val = m.diameter_mm  # type: ignore[assignment]
        t = self._t.diameter

        # Check minimum
        if val <= t.min_critical_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type="DIAMETER_LOW",
                value=val,
                threshold=t.min_critical_mm,
                severity="CRITICAL",
                message=f"Diameter {val:.2f} mm below CRITICAL minimum {t.min_critical_mm} mm",
            ))
        elif val <= t.min_warning_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type="DIAMETER_LOW",
                value=val,
                threshold=t.min_warning_mm,
                severity="WARNING",
                message=f"Diameter {val:.2f} mm below WARNING minimum {t.min_warning_mm} mm",
            ))

        # Check maximum
        if val >= t.max_critical_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type="DIAMETER_HIGH",
                value=val,
                threshold=t.max_critical_mm,
                severity="CRITICAL",
                message=f"Diameter {val:.2f} mm above CRITICAL maximum {t.max_critical_mm} mm",
            ))
        elif val >= t.max_warning_mm:
            results.append(Anomaly(
                frame_id=m.frame_id,
                timestamp_ms=m.timestamp_ms,
                anomaly_type="DIAMETER_HIGH",
                value=val,
                threshold=t.max_warning_mm,
                severity="WARNING",
                message=f"Diameter {val:.2f} mm above WARNING maximum {t.max_warning_mm} mm",
            ))

        return results

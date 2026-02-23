"""tests/unit/test_rules.py — RulesEngine threshold evaluation tests."""

import pytest

from ohe.core.config import RulesConfig, StaggerThreshold, DiameterThreshold
from ohe.core.models import Measurement
from ohe.rules.engine import RulesEngine
from ohe.rules.thresholds import Thresholds


def make_thresholds() -> Thresholds:
    rc = RulesConfig(
        stagger=StaggerThreshold(warning_mm=150.0, critical_mm=200.0),
        diameter=DiameterThreshold(
            min_warning_mm=10.0, min_critical_mm=8.0,
            max_warning_mm=15.0, max_critical_mm=17.0,
        ),
    )
    return Thresholds.from_config(rc)


def make_measurement(stagger=0.0, diameter=12.0, confidence=0.9) -> Measurement:
    return Measurement(
        frame_id=1,
        timestamp_ms=33.0,
        stagger_mm=stagger,
        diameter_mm=diameter,
        confidence=confidence,
    )


class TestStaggerRules:
    def setup_method(self):
        self.engine = RulesEngine(make_thresholds())

    def test_no_anomaly_within_limits(self):
        anomalies = self.engine.evaluate(make_measurement(stagger=100.0))
        assert anomalies == []

    def test_stagger_right_warning(self):
        anomalies = self.engine.evaluate(make_measurement(stagger=160.0))
        assert len(anomalies) == 1
        assert anomalies[0].anomaly_type == "STAGGER_RIGHT"
        assert anomalies[0].severity == "WARNING"

    def test_stagger_right_critical(self):
        anomalies = self.engine.evaluate(make_measurement(stagger=210.0))
        assert any(a.severity == "CRITICAL" for a in anomalies)

    def test_stagger_left_warning(self):
        anomalies = self.engine.evaluate(make_measurement(stagger=-160.0))
        assert anomalies[0].anomaly_type == "STAGGER_LEFT"
        assert anomalies[0].severity == "WARNING"

    def test_exactly_at_warning_boundary(self):
        anomalies = self.engine.evaluate(make_measurement(stagger=150.0))
        assert len(anomalies) == 1


class TestDiameterRules:
    def setup_method(self):
        self.engine = RulesEngine(make_thresholds())

    def test_no_anomaly_normal_diameter(self):
        assert self.engine.evaluate(make_measurement(diameter=12.0)) == []

    def test_diameter_low_warning(self):
        anomalies = self.engine.evaluate(make_measurement(diameter=9.5))
        assert anomalies[0].anomaly_type == "DIAMETER_LOW"
        assert anomalies[0].severity == "WARNING"

    def test_diameter_low_critical(self):
        anomalies = self.engine.evaluate(make_measurement(diameter=7.5))
        assert anomalies[0].severity == "CRITICAL"

    def test_diameter_high_warning(self):
        anomalies = self.engine.evaluate(make_measurement(diameter=15.5))
        assert anomalies[0].anomaly_type == "DIAMETER_HIGH"

    def test_diameter_high_critical(self):
        anomalies = self.engine.evaluate(make_measurement(diameter=18.0))
        assert anomalies[0].severity == "CRITICAL"

    def test_null_diameter_skipped(self):
        m = Measurement(1, 0.0, stagger_mm=0.0, diameter_mm=None, confidence=0.9)
        assert self.engine.evaluate(m) == []

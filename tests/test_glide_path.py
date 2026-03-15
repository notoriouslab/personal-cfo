"""Tests for retirement glide path engine."""

import pytest
from personal_cfo.glide_path import (
    target_equity_ratio, diagnose_drift, glide_path_table,
)


def _cfg(birth=1970, retire=65, equity=0.20, derisking=0.01,
         floor=0.05, tolerance=0.03, warning=0.05, baseline=2026):
    return {
        "life_plan": {"birth_year": birth, "retirement_age": retire},
        "glide_path": {
            "equity_target": equity,
            "annual_derisking": derisking,
            "min_equity_floor": floor,
            "drift_tolerance": tolerance,
            "drift_warning": warning,
            "baseline_year": baseline,
        },
    }


class TestTargetEquityRatio:
    def test_at_baseline_age(self):
        """At baseline age, target should equal equity_target."""
        cfg = _cfg(birth=1970, baseline=2026)  # age 56
        assert target_equity_ratio(56, cfg) == pytest.approx(0.20)

    def test_one_year_later(self):
        cfg = _cfg(birth=1970, baseline=2026)
        assert target_equity_ratio(57, cfg) == pytest.approx(0.19)

    def test_ten_years_later(self):
        cfg = _cfg(birth=1970, baseline=2026)
        assert target_equity_ratio(66, cfg) == pytest.approx(0.10)

    def test_floor_respected(self):
        cfg = _cfg(birth=1970, baseline=2026, equity=0.20, floor=0.05)
        # At age 71, target = 0.20 - 15*0.01 = 0.05 (exactly floor)
        assert target_equity_ratio(71, cfg) == pytest.approx(0.05)
        # At age 80, should still be 0.05 (floored)
        assert target_equity_ratio(80, cfg) == pytest.approx(0.05)

    def test_younger_than_baseline_clamped(self):
        """Bug fix: querying age < baseline should not increase target."""
        cfg = _cfg(birth=1970, baseline=2026)  # baseline age = 56
        # Age 50 is younger than baseline — should clamp at equity_target
        assert target_equity_ratio(50, cfg) == pytest.approx(0.20)

    def test_young_aggressive(self):
        """Young person with high equity target."""
        cfg = _cfg(birth=1996, baseline=2026, equity=0.60)  # age 30
        assert target_equity_ratio(30, cfg) == pytest.approx(0.60)
        assert target_equity_ratio(40, cfg) == pytest.approx(0.50)

    def test_no_baseline_year_uses_current(self):
        """When baseline_year not set, defaults to current year."""
        from datetime import datetime
        cfg = _cfg(birth=1980)
        del cfg["glide_path"]["baseline_year"]
        current_age = datetime.now().year - 1980
        assert target_equity_ratio(current_age, cfg) == pytest.approx(0.20)


class TestDiagnoseDrift:
    def test_on_track(self):
        cfg = _cfg()
        result = diagnose_drift(0.19, cfg)  # target=0.20, drift=-0.01
        assert result.status == "on_track"

    def test_minor_drift(self):
        cfg = _cfg()
        result = diagnose_drift(0.16, cfg)  # target=0.20, drift=-0.04
        assert result.status == "minor_drift"

    def test_major_drift(self):
        cfg = _cfg()
        result = diagnose_drift(0.10, cfg)  # target=0.20, drift=-0.10
        assert result.status == "major_drift"

    def test_overweight_minor(self):
        cfg = _cfg()
        result = diagnose_drift(0.24, cfg)  # +0.04
        assert result.status == "minor_drift"
        assert "偏高" in result.message

    def test_underweight_major(self):
        cfg = _cfg()
        result = diagnose_drift(0.05, cfg)  # -0.15
        assert result.status == "major_drift"
        assert "偏低" in result.message


class TestGlidePathTable:
    def test_returns_tuples(self):
        cfg = _cfg()
        table = glide_path_table(cfg, from_age=56, to_age=60)
        assert len(table) == 5
        assert all(isinstance(t, tuple) and len(t) == 2 for t in table)

    def test_decreasing_target(self):
        cfg = _cfg()
        table = glide_path_table(cfg, from_age=56, to_age=66)
        targets = [t[1] for t in table]
        # Should be monotonically non-increasing
        for i in range(len(targets) - 1):
            assert targets[i] >= targets[i + 1]

    def test_default_range(self):
        cfg = _cfg(retire=65)
        table = glide_path_table(cfg)
        # Default to_age = retirement_age + 6 = 71
        last_age = table[-1][0]
        assert last_age == 71

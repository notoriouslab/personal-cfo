"""Tests for retirement projection engine."""

import pytest
from personal_cfo.projection import (
    weighted_portfolio_return, split_liquid_illiquid,
    rebalance_buckets, run_projection, projection_summary,
)
from personal_cfo.report import render_projection_report


def _cfg(birth=1980, retire=65, life_exp=84, monthly=100000,
         inflation=0.025, savings=0):
    return {
        "life_plan": {
            "birth_year": birth,
            "retirement_age": retire,
            "life_expectancy": life_exp,
        },
        "glide_path": {
            "equity_target": 0.20,
            "annual_derisking": 0.01,
            "min_equity_floor": 0.05,
            "drift_tolerance": 0.03,
            "drift_warning": 0.05,
        },
        "assumptions": {
            "monthly_expense": monthly,
            "base_currency": "TWD",
            "inflation_rate": inflation,
            "annual_savings": savings,
        },
        "projection": {
            "expected_returns": {
                "equities": 0.07,
                "bonds": 0.03,
                "real_estate": 0.03,
                "liquid_cash": 0.015,
                "insurance": 0.02,
                "other": 0.01,
            },
        },
    }


def _snap(net_worth=20000000, liquid_cash=300000, equities=500000,
          bonds=200000, real_estate=18000000, period="2026-01"):
    return {
        "period": period,
        "net_worth": net_worth,
        "total_assets": net_worth + 1000000,
        "total_liabilities": 1000000,
        "total_cash": liquid_cash,
        "equity_ratio": 0.5,
        "risk_buckets": {
            "liquid_cash": liquid_cash,
            "equities": equities,
            "bonds": bonds,
            "real_estate": real_estate,
            "insurance": 0,
            "other": 0,
        },
    }


class TestWeightedPortfolioReturn:
    def test_all_equities(self):
        buckets = {"equities": 100000}
        er = {"equities": 0.07}
        assert weighted_portfolio_return(buckets, er) == pytest.approx(0.07)

    def test_mixed(self):
        buckets = {"equities": 50000, "bonds": 50000}
        er = {"equities": 0.07, "bonds": 0.03}
        assert weighted_portfolio_return(buckets, er) == pytest.approx(0.05)

    def test_excludes_real_estate(self):
        buckets = {"equities": 100000, "real_estate": 10000000}
        er = {"equities": 0.07, "real_estate": 0.03}
        assert weighted_portfolio_return(buckets, er) == pytest.approx(0.07)

    def test_zero_total(self):
        assert weighted_portfolio_return({}, {"equities": 0.07}) == 0.0

    def test_missing_bucket_rate(self):
        buckets = {"equities": 100000, "other": 50000}
        er = {"equities": 0.07}  # "other" not in expected_returns
        # other gets 0.0 return, weighted = (100k*0.07 + 50k*0.0) / 150k
        assert weighted_portfolio_return(buckets, er) == pytest.approx(
            7000 / 150000)


class TestSplitLiquidIlliquid:
    def test_normal(self):
        buckets = {"liquid_cash": 300000, "equities": 500000,
                   "real_estate": 18000000, "bonds": 200000}
        liquid, illiquid = split_liquid_illiquid(buckets)
        assert liquid == 1000000
        assert illiquid == 18000000

    def test_no_real_estate(self):
        buckets = {"liquid_cash": 500000, "equities": 500000}
        liquid, illiquid = split_liquid_illiquid(buckets)
        assert liquid == 1000000
        assert illiquid == 0

    def test_only_real_estate(self):
        buckets = {"real_estate": 20000000}
        liquid, illiquid = split_liquid_illiquid(buckets)
        assert liquid == 0
        assert illiquid == 20000000

    def test_negative_amounts_ignored(self):
        buckets = {"liquid_cash": 500000, "equities": -100}
        liquid, illiquid = split_liquid_illiquid(buckets)
        assert liquid == 500000


class TestRebalanceBuckets:
    def test_equity_ratio(self):
        cfg = _cfg()
        result = rebalance_buckets(1000000, 46, cfg)
        # At age 46, target equity = 0.20 (baseline)
        assert result["equities"] == pytest.approx(200000)
        assert result["bonds"] + result["liquid_cash"] == pytest.approx(800000)

    def test_real_estate_not_included(self):
        cfg = _cfg()
        result = rebalance_buckets(1000000, 50, cfg)
        assert "real_estate" not in result or result.get("real_estate", 0) == 0


class TestRunProjection:
    def test_basic_lifecycle(self):
        cfg = _cfg(birth=1980, retire=65, life_exp=70, monthly=50000)
        snap = _snap(liquid_cash=5000000, equities=3000000,
                     bonds=2000000, real_estate=0, net_worth=10000000)
        rows = run_projection(snap, cfg)
        assert len(rows) == 70 - 46 + 1  # age 46 to 70 inclusive
        assert rows[0].age == 46
        assert rows[0].phase == "accumulation"
        assert rows[-1].age == 70
        assert rows[-1].phase == "retirement"

    def test_accumulation_grows(self):
        cfg = _cfg(birth=1980, retire=65, life_exp=67,
                   monthly=50000, savings=500000)
        snap = _snap(liquid_cash=5000000, equities=0,
                     bonds=0, real_estate=0, net_worth=5000000)
        rows = run_projection(snap, cfg)
        # With savings and returns, net worth should grow during accumulation
        accum = [r for r in rows if r.phase == "accumulation"]
        assert accum[-1].net_worth > accum[0].net_worth

    def test_retirement_depletes(self):
        cfg = _cfg(birth=1980, retire=46, life_exp=60,
                   monthly=200000)  # high expense, already retired
        snap = _snap(liquid_cash=500000, equities=0,
                     bonds=0, real_estate=0, net_worth=500000,
                     period="2026-01")
        rows = run_projection(snap, cfg)
        # Should deplete quickly with 200k/month = 2.4M/year on 500k
        assert any(r.depleted for r in rows)

    def test_real_estate_not_liquidated(self):
        cfg = _cfg(birth=1980, retire=46, life_exp=50, monthly=100000)
        snap = _snap(liquid_cash=100000, equities=0, bonds=0,
                     real_estate=20000000, net_worth=20100000)
        rows = run_projection(snap, cfg)
        depleted_rows = [r for r in rows if r.depleted]
        # Liquid depletes but net_worth stays positive (real estate)
        if depleted_rows:
            assert depleted_rows[0].net_worth > 0
            assert depleted_rows[0].illiquid_assets > 0

    def test_inflation_compounds(self):
        cfg = _cfg(birth=1980, retire=46, life_exp=56,
                   monthly=100000, inflation=0.10)  # 10% inflation
        snap = _snap(liquid_cash=50000000, equities=0, bonds=0,
                     real_estate=0, net_worth=50000000)
        rows = run_projection(snap, cfg)
        # After 10 years at 10% inflation, expense should roughly 2.59x
        assert rows[-1].annual_expense > rows[0].annual_expense * 2.5

    def test_zero_savings_conservative(self):
        cfg = _cfg(savings=0)
        snap = _snap()
        rows = run_projection(snap, cfg)
        accum = [r for r in rows if r.phase == "accumulation"]
        for r in accum:
            assert r.net_flow == 0  # no savings


class TestProjectionSummary:
    def test_sustainable(self):
        cfg = _cfg(birth=1980, retire=65, life_exp=67, monthly=10000)
        snap = _snap(liquid_cash=50000000, equities=0, bonds=0,
                     real_estate=0, net_worth=50000000)
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        assert s["sustainability"] == "sustainable"
        assert s["depleted_age"] is None

    def test_depleted(self):
        cfg = _cfg(birth=1980, retire=46, life_exp=60, monthly=200000)
        snap = _snap(liquid_cash=500000, equities=0, bonds=0,
                     real_estate=0, net_worth=500000)
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        assert s["sustainability"] == "depleted"
        assert s["depleted_age"] is not None
        assert s["depleted_age"] < 60

    def test_years_calculation(self):
        cfg = _cfg(birth=1980, retire=65, life_exp=84)
        snap = _snap(period="2026-01")
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        assert s["current_age"] == 46
        assert s["years_to_retirement"] == 19
        assert s["years_in_retirement"] == 19


class TestRenderProjectionReport:
    def test_contains_all_sections(self):
        cfg = _cfg()
        snap = _snap()
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        report = render_projection_report(snap, rows, s, cfg)
        assert "退休投影報告" in report
        assert "免責聲明" in report
        assert "假設參數" in report
        assert "退休準備度" in report
        assert "年度投影" in report
        assert "注意事項" in report

    def test_depletion_warning(self):
        cfg = _cfg(birth=1980, retire=46, life_exp=60, monthly=200000)
        snap = _snap(liquid_cash=500000, equities=0, bonds=0,
                     real_estate=0, net_worth=500000)
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        report = render_projection_report(snap, rows, s, cfg)
        assert "資金不足" in report
        assert "⚠️" in report

    def test_real_estate_warning(self):
        cfg = _cfg()
        snap = _snap(real_estate=20000000)
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        report = render_projection_report(snap, rows, s, cfg)
        assert "不動產" in report
        assert "不可提領" in report

    def test_sustainable_shows_green(self):
        cfg = _cfg(birth=1980, retire=65, life_exp=67, monthly=10000)
        snap = _snap(liquid_cash=50000000, equities=0, bonds=0,
                     real_estate=0, net_worth=50000000)
        rows = run_projection(snap, cfg)
        s = projection_summary(rows, cfg)
        report = render_projection_report(snap, rows, s, cfg)
        assert "可持續" in report

"""Tests for report rendering — CFO and track reports."""

import pytest
from personal_cfo.report import (
    render_cfo_report, render_track_report, _savings_rate,
    _render_bucket_detail, _fmt, _pct,
)
from personal_cfo.accounting import (
    IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL, IS_LIVING,
    IS_CAPEX, IS_PRINCIPAL, IS_INTEREST, IS_FEES,
)
from personal_cfo.models import BalanceSheet, CashFlow, ClassifiedTx, GlideDiagnosis


def _make_cfg():
    return {
        "assumptions": {"base_currency": "TWD", "monthly_expense": 100000},
        "life_plan": {"birth_year": 1980, "retirement_age": 65},
        "glide_path": {
            "equity_target": 0.20,
            "annual_derisking": 0.01,
            "min_equity_floor": 0.05,
            "drift_tolerance": 0.03,
            "drift_warning": 0.05,
            "baseline_year": 2026,
        },
    }


class TestFormatters:
    def test_fmt(self):
        assert _fmt(1234567) == "1,234,567"

    def test_fmt_negative(self):
        assert _fmt(-50000) == "-50,000"

    def test_pct(self):
        assert _pct(0.425) == "42.5%"


class TestSavingsRate:
    def test_normal(self):
        buckets = {IS_SALARY: 150000, IS_INVEST_INCOME: 0,
                   IS_LIVING: -80000, IS_PRINCIPAL: 0,
                   IS_INTEREST: 0, IS_FEES: 0}
        rate = _savings_rate(buckets)
        assert rate == pytest.approx((150000 - 80000) / 150000)

    def test_zero_revenue(self):
        buckets = {IS_SALARY: 0, IS_INVEST_INCOME: 0,
                   IS_LIVING: -80000, IS_PRINCIPAL: 0,
                   IS_INTEREST: 0, IS_FEES: 0}
        assert _savings_rate(buckets) == 0

    def test_negative_revenue(self):
        buckets = {IS_SALARY: -5000, IS_INVEST_INCOME: 0,
                   IS_LIVING: -80000, IS_PRINCIPAL: 0,
                   IS_INTEREST: 0, IS_FEES: 0}
        assert _savings_rate(buckets) == 0

    def test_expense_exceeds_revenue(self):
        buckets = {IS_SALARY: 10000, IS_INVEST_INCOME: 0,
                   IS_LIVING: -80000, IS_PRINCIPAL: 0,
                   IS_INTEREST: 0, IS_FEES: 0}
        assert _savings_rate(buckets) == 0


class TestRenderBucketDetail:
    def test_shows_items(self):
        txs = [
            ClassifiedTx(date="2026-01-05", description="Salary",
                        amount_twd=150000, currency="TWD",
                        amount_orig=150000, account="A", bucket=IS_SALARY),
        ]
        lines = _render_bucket_detail(txs, IS_SALARY)
        assert len(lines) == 1
        assert "Salary" in lines[0]

    def test_max_items_truncation(self):
        txs = [
            ClassifiedTx(date="", description=f"Item {i}",
                        amount_twd=1000 * i, currency="TWD",
                        amount_orig=1000 * i, account="A", bucket=IS_LIVING)
            for i in range(1, 16)
        ]
        lines = _render_bucket_detail(txs, IS_LIVING, max_items=5)
        assert len(lines) == 6  # 5 items + "...其他 10 筆"
        assert "其他" in lines[-1]

    def test_empty_bucket(self):
        txs = [
            ClassifiedTx(date="", description="X", amount_twd=100,
                        currency="TWD", amount_orig=100, account="A",
                        bucket=IS_SALARY),
        ]
        lines = _render_bucket_detail(txs, IS_LIVING)
        assert lines == []


class TestRenderCfoReport:
    def test_basic_report(self):
        cfg = _make_cfg()
        is_buckets = {
            IS_SALARY: 150000, IS_INVEST_INCOME: 6000,
            IS_CAPITAL: -100000, IS_LIVING: -50000,
            IS_CAPEX: -30000, IS_PRINCIPAL: -25000,
            IS_INTEREST: -5000, IS_FEES: -200,
        }
        bs = BalanceSheet(
            details=[], risk_buckets={"liquid_cash": 1000000, "equities": 500000,
                                       "bonds": 0, "real_estate": 0,
                                       "insurance": 0, "other": 0},
            total_assets=1500000, total_liabilities=0,
            net_worth=1500000, total_cash=1000000,
        )
        cf = CashFlow(inflow=156000, outflow=-80200, net_flow=75800)
        glide = GlideDiagnosis(age=46, target=0.20, actual=0.33,
                               drift=0.13, abs_drift=0.13,
                               status="major_drift",
                               message="Equity allocation significantly off target.")
        market = {"US_10Y_Yield": 4.13, "BTC_USD": 67809.0, "USD_TWD": 31.91}
        report = render_cfo_report("2026-01", is_buckets, bs, cf,
                                    market, glide, cfg)
        assert "# 財務報告" in report
        assert "損益表" in report
        assert "資產負債表" in report
        assert "現金流量" in report
        assert "退休軌道" in report
        assert "市場定錨" in report

    def test_no_balance_sheet(self):
        cfg = _make_cfg()
        is_buckets = {IS_SALARY: 150000, IS_INVEST_INCOME: 0,
                      IS_CAPITAL: 0, IS_LIVING: -50000,
                      IS_CAPEX: 0, IS_PRINCIPAL: 0,
                      IS_INTEREST: 0, IS_FEES: 0}
        cf = CashFlow(inflow=150000, outflow=-50000, net_flow=100000)
        report = render_cfo_report("2026-01", is_buckets, None, cf,
                                    {}, None, cfg)
        assert "資產負債表" not in report

    def test_with_warnings(self):
        cfg = _make_cfg()
        is_buckets = {k: 0 for k in [IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL,
                                       IS_LIVING, IS_CAPEX, IS_PRINCIPAL,
                                       IS_INTEREST, IS_FEES]}
        cf = CashFlow(inflow=0, outflow=0, net_flow=0)
        report = render_cfo_report("2026-01", is_buckets, None, cf,
                                    {}, None, cfg,
                                    warnings=["Test warning"])
        assert "Test warning" in report


class TestRenderTrackReport:
    def test_basic_track(self):
        cfg = _make_cfg()
        snapshots = [
            {"period": "2026-01", "net_worth": 5000000,
             "equity_ratio": 0.20, "glide_path": {"status": "on_track"}},
            {"period": "2026-02", "net_worth": 5100000,
             "equity_ratio": 0.21, "glide_path": {"status": "on_track"}},
        ]
        glide = GlideDiagnosis(age=46, target=0.20, actual=0.21,
                               drift=0.01, abs_drift=0.01,
                               status="on_track",
                               message="Equity allocation is within target range.")
        report = render_track_report(snapshots, glide, cfg)
        assert "Track Audit" in report
        assert "Trend" in report
        assert "Glide Path Table" in report

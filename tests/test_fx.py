"""Tests for FX engine."""

import pytest
from personal_cfo.fx import make_fx


class TestMakeFx:
    def test_twd_passthrough(self):
        to_twd = make_fx({"USD_TWD": 32.0})
        assert to_twd("TWD", 100000) == 100000.0

    def test_usd_conversion(self):
        to_twd = make_fx({"USD_TWD": 32.0})
        assert to_twd("USD", 1000) == pytest.approx(32000.0)

    def test_case_insensitive(self):
        to_twd = make_fx({"USD_TWD": 32.0})
        assert to_twd("usd", 100) == pytest.approx(3200.0)

    def test_missing_currency_warns_and_uses_1(self, capsys):
        to_twd = make_fx({})
        result = to_twd("EUR", 100)
        assert result == 100.0  # rate=1.0 fallback
        captured = capsys.readouterr()
        assert "No exchange rate for EUR" in captured.err

    def test_missing_currency_warns_only_once(self, capsys):
        """Each make_fx instance has its own warning set (closure-scoped)."""
        to_twd = make_fx({})
        to_twd("GBP", 100)
        to_twd("GBP", 200)
        captured = capsys.readouterr()
        assert captured.err.count("WARNING") == 1

    def test_separate_instances_warn_independently(self, capsys):
        """Different make_fx instances should each warn independently."""
        to_twd_a = make_fx({})
        to_twd_b = make_fx({})
        to_twd_a("CHF", 100)
        to_twd_b("CHF", 100)
        captured = capsys.readouterr()
        assert captured.err.count("WARNING") == 2

    def test_multiple_currencies(self):
        to_twd = make_fx({"USD_TWD": 32.0, "JPY_TWD": 0.21})
        assert to_twd("USD", 1000) == pytest.approx(32000.0)
        assert to_twd("JPY", 10000) == pytest.approx(2100.0)

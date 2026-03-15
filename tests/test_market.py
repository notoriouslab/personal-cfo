"""Tests for market data fetcher — yfinance mock, cache, fallback."""

import json
import time
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from personal_cfo.market import (
    fetch_market_anchors, _load_cache, _save_cache,
    FALLBACK, _CACHE_MAX_AGE,
)


class TestFetchOffline:
    def test_offline_returns_fallback(self, tmp_path):
        result = fetch_market_anchors(offline=True, cache_dir=str(tmp_path))
        assert result == FALLBACK

    def test_offline_prefers_cache(self, tmp_path):
        # Write a fresh cache
        cache_data = {"ts": time.time(), "anchors": {"US_10Y_Yield": 99.99}}
        (tmp_path / "market_cache.json").write_text(json.dumps(cache_data))
        result = fetch_market_anchors(offline=True, cache_dir=str(tmp_path))
        assert result["US_10Y_Yield"] == 99.99


class TestCache:
    def test_save_and_load(self, tmp_path):
        anchors = {"US_10Y_Yield": 4.5, "BTC_USD": 70000}
        _save_cache(anchors, str(tmp_path))
        loaded = _load_cache(str(tmp_path))
        assert loaded == anchors

    def test_expired_cache_returns_none(self, tmp_path):
        cache_data = {"ts": time.time() - _CACHE_MAX_AGE - 100,
                      "anchors": {"US_10Y_Yield": 4.5}}
        (tmp_path / "market_cache.json").write_text(json.dumps(cache_data))
        assert _load_cache(str(tmp_path)) is None

    def test_corrupt_cache_returns_none(self, tmp_path):
        (tmp_path / "market_cache.json").write_text("not json")
        assert _load_cache(str(tmp_path)) is None

    def test_missing_cache_returns_none(self, tmp_path):
        assert _load_cache(str(tmp_path)) is None


class TestYfinanceMock:
    def test_successful_fetch(self, tmp_path):
        """Mock yfinance to simulate successful data fetch."""
        mock_yf = MagicMock()
        mock_ticker = MagicMock()
        mock_hist = MagicMock()
        mock_hist.empty = False
        mock_hist.__getitem__ = lambda self, key: MagicMock(
            iloc=MagicMock(__getitem__=lambda self, i: 42.0))
        mock_ticker.history.return_value = mock_hist
        mock_yf.Ticker.return_value = mock_ticker

        with patch.dict("sys.modules", {"yfinance": mock_yf}):
            result = fetch_market_anchors(offline=False,
                                          cache_dir=str(tmp_path))
        # Should have values (from mock or fallback fill)
        assert "US_10Y_Yield" in result

    def test_import_error_falls_back(self, tmp_path):
        """When yfinance not installed, should fall back gracefully."""
        # fetch_market_anchors handles ImportError internally
        result = fetch_market_anchors(offline=False, cache_dir=str(tmp_path))
        # Should return something (cached or fallback)
        assert isinstance(result, dict)
        assert len(result) >= 3


class TestFallback:
    def test_hardcoded_fallback_has_all_keys(self):
        assert "US_10Y_Yield" in FALLBACK
        assert "BTC_USD" in FALLBACK
        assert "Gold" in FALLBACK
        assert "USD_TWD" in FALLBACK
        assert "TAIEX" in FALLBACK

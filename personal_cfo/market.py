"""Market anchors — global indicators for context. Uses yfinance with 3-tier fallback."""

import json
import os
import tempfile
import time
from pathlib import Path

TICKERS = {
    "US_10Y_Yield": "^TNX",
    "BTC_USD": "BTC-USD",
    "Gold": "GC=F",
    "USD_TWD": "TWD=X",
    "TAIEX": "^TWII",
}

# Hardcoded fallback values (as of 2026-03-01). Update periodically.
FALLBACK = {
    "US_10Y_Yield": 4.13,
    "BTC_USD": 67809.0,
    "Gold": 5146.0,
    "USD_TWD": 31.91,
    "TAIEX": 33600.0,
}

_CACHE_FILENAME = "market_cache.json"
_CACHE_MAX_AGE = 24 * 3600  # 24 hours


def _cache_path(cache_dir):
    """Resolve cache file path from explicit dir."""
    return Path(cache_dir) / _CACHE_FILENAME


def _load_cache(cache_dir):
    """Load cached market data if fresh enough."""
    try:
        p = _cache_path(cache_dir)
        if p.exists():
            data = json.loads(p.read_text())
            age = time.time() - data.get("ts", 0)
            if age < _CACHE_MAX_AGE:
                return data.get("anchors", {})
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _save_cache(anchors, cache_dir):
    """Save market data to cache atomically."""
    try:
        p = _cache_path(cache_dir)
        p.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps({"ts": time.time(), "anchors": anchors})
        fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
        closed = False
        try:
            os.write(fd, content.encode("utf-8"))
            os.close(fd)
            closed = True
            os.replace(tmp, str(p))
        except Exception:
            if not closed:
                try:
                    os.close(fd)
                except OSError:
                    pass
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
    except OSError:
        pass


def fetch_market_anchors(offline=False, cache_dir=None):
    """Fetch market anchors with 3-tier fallback: yfinance → cache → hardcoded.

    Args:
        offline: skip network calls
        cache_dir: directory for cache file (default: .cache/ under CWD)

    Returns dict of {indicator_name: value}.
    """
    if cache_dir is None:
        cache_dir = os.path.join(".", ".cache")

    # Tier 2: cache
    cached = _load_cache(cache_dir)

    if offline:
        return cached or dict(FALLBACK)

    # Tier 1: yfinance
    try:
        import yfinance as yf

        anchors = {}
        for name, ticker in TICKERS.items():
            try:
                t = yf.Ticker(ticker)
                hist = t.history(period="5d")
                if not hist.empty:
                    anchors[name] = round(float(hist["Close"].iloc[-1]), 2)
            except Exception:
                pass

        if len(anchors) >= 3:  # got enough data
            _save_cache(anchors, cache_dir)
            # Fill missing with fallback
            for k, v in FALLBACK.items():
                anchors.setdefault(k, v)
            return anchors
    except ImportError:
        pass
    except Exception:
        pass

    # Tier 2: cache
    if cached:
        return cached

    # Tier 3: hardcoded fallback
    return dict(FALLBACK)

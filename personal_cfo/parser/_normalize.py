"""Shared normalization helpers — amounts, dates, currencies, classification."""

import math
import re


def _clean_amount(val):
    """Convert amount string to float, stripping commas and whitespace."""
    if isinstance(val, (int, float)):
        v = float(val)
    else:
        s = str(val).strip().replace(",", "").replace(" ", "")
        # Strip bold markdown, dollar sign, parenthetical notes
        s = s.replace("**", "").replace("$", "").strip()
        if not s or s == "-":
            return 0.0
        # Remove trailing parenthetical like "(97.38%)"
        s = re.sub(r"\(.*?\)$", "", s).strip()
        if not s:
            return 0.0
        v = float(s)
    # Reject NaN, Inf, and absurdly large values
    if math.isnan(v) or math.isinf(v) or abs(v) > 1e12:
        raise ValueError(f"Invalid amount: {val}")
    return v


def _classify(description, category_rules):
    """Match description against keyword rules. Returns category or None."""
    desc_lower = description.lower()
    for keyword, category in category_rules.items():
        if keyword.lower() in desc_lower:
            return category
    return None


_CURRENCY_MAP = {
    "臺幣": "TWD", "台幣": "TWD", "新臺幣": "TWD",
    "美元": "USD", "美金": "USD",
    "澳幣": "AUD", "澳元": "AUD",
    "日圓": "JPY", "日幣": "JPY", "日元": "JPY",
    "歐元": "EUR", "英鎊": "GBP", "人民幣": "CNY",
    "泰銖": "THB", "港幣": "HKD", "加幣": "CAD",
}


def _normalize_currency(raw):
    """Map Chinese currency names to ISO codes."""
    raw = raw.strip().replace("**", "")
    up = raw.upper()
    if up in ("TWD", "USD", "AUD", "JPY", "EUR", "GBP", "CNY", "THB", "HKD", "CAD"):
        return up
    return _CURRENCY_MAP.get(raw, "TWD")


def _detect_currency_from_desc(desc):
    """Detect currency from description hints.

    Handles patterns like:
    - "基金配息 (CNY)" → CNY
    - "INTEREST (USD)" → USD
    - "美元活存: 信託 法興 SN718" → USD
    - "澳元活存: 利息" → AUD
    - "台幣活存: 繳放款" → TWD

    Returns ISO currency code or None if no hint found.
    Note: "折TWD" in description means amount was already converted to TWD.
    """
    # Parenthetical ISO code at end: "(CNY)", "(USD)", etc.
    m = re.search(r'\(([A-Z]{3})\)\s*$', desc)
    if m:
        code = m.group(1)
        if code in ("TWD", "USD", "AUD", "JPY", "EUR", "GBP", "CNY", "THB", "HKD", "CAD"):
            return code

    # Chinese account prefix: "美元活存:", "澳元定存:", etc.
    _PREFIX_CURRENCY = {
        "美元活存": "USD", "美元定存": "USD", "美金活存": "USD",
        "澳元活存": "AUD", "澳幣活存": "AUD", "澳元定存": "AUD",
        "日圓活存": "JPY", "日幣活存": "JPY", "日圓定存": "JPY",
        "人民幣活存": "CNY", "人民幣定存": "CNY",
        "歐元活存": "EUR", "歐元定存": "EUR",
        "台幣活存": "TWD", "臺幣活存": "TWD", "台幣定存": "TWD",
    }
    for prefix, cur in _PREFIX_CURRENCY.items():
        if desc.startswith(prefix):
            # "折TWD" means the amount is already in TWD despite the account currency
            if "折TWD" in desc or "折臺幣" in desc:
                return "TWD"
            return cur

    return None


def _normalize_date(raw):
    """Convert YYYY/MM/DD to YYYY-MM-DD."""
    raw = raw.strip()
    if "/" in raw:
        return raw.replace("/", "-")
    return raw

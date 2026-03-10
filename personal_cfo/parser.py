"""Parse financial data from CSV or Markdown+JSON (doc-cleaner output).

Supports three input modes:
1. CSV — universal, user-provided
2. Markdown with transactions[]/assets[] JSON — pre-structured
3. Markdown with refined_markdown only — fallback, extracts from pipe tables
"""

import csv
import json
import io
import re
import sys
from pathlib import Path


def _try_read(path):
    """Read file trying common encodings."""
    for enc in ("utf-8-sig", "utf-8", "big5", "cp950"):
        try:
            return Path(path).read_text(encoding=enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
    raise ValueError(f"Cannot decode file: {Path(path).name}")


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
    import math
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


# ---------- Pipe table helpers (for refined_markdown fallback) ----------

_CURRENCY_MAP = {
    "臺幣": "TWD", "台幣": "TWD", "新臺幣": "TWD",
    "美元": "USD", "美金": "USD",
    "澳幣": "AUD", "澳元": "AUD",
    "日圓": "JPY", "日幣": "JPY", "日元": "JPY",
    "歐元": "EUR", "英鎊": "GBP", "人民幣": "CNY",
    "泰銖": "THB", "港幣": "HKD", "加幣": "CAD",
}

# Column header keywords for detection
_DATE_KEYWORDS = ("消費日", "交易日", "日期", "date")
_DESC_KEYWORDS = ("帳單說明", "說明", "摘要", "description")
_AMOUNT_KEYWORDS = ("臺幣金額", "台幣金額", "金額", "amount")
_DEBIT_KEYWORDS = ("支出",)
_CREDIT_KEYWORDS = ("存入",)
_CURRENCY_KEYWORDS = ("幣別",)


def _find_col(headers, keywords):
    """Find first column index whose header contains any keyword."""
    for i, h in enumerate(headers):
        h_clean = h.strip().replace("**", "").lower()
        for kw in keywords:
            if kw.lower() in h_clean:
                return i
    return None


def _normalize_currency(raw):
    """Map Chinese currency names to ISO codes."""
    raw = raw.strip().replace("**", "")
    up = raw.upper()
    if up in ("TWD", "USD", "AUD", "JPY", "EUR", "GBP", "CNY", "THB", "HKD", "CAD"):
        return up
    return _CURRENCY_MAP.get(raw, "TWD")


def _normalize_date(raw):
    """Convert YYYY/MM/DD to YYYY-MM-DD."""
    raw = raw.strip()
    if "/" in raw:
        return raw.replace("/", "-")
    return raw


def _parse_tables_from_markdown(md_text, is_cc=False, vendor="",
                                category_rules=None):
    """Extract transactions from pipe tables in refined_markdown.

    Detects two table formats:
    - Single amount column (credit card): date | desc | amount
    - Split debit/credit columns (bank): date | desc | debit | credit | balance
    """
    transactions = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            i += 1
            continue

        # Collect consecutive pipe-table lines
        table_lines = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            table_lines.append(lines[i].strip())
            i += 1

        if len(table_lines) < 3:  # header + separator + 1+ data rows
            continue

        # Parse header row
        headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]

        # Detect transaction columns
        date_col = _find_col(headers, _DATE_KEYWORDS)
        desc_col = _find_col(headers, _DESC_KEYWORDS)
        amount_col = _find_col(headers, _AMOUNT_KEYWORDS)
        debit_col = _find_col(headers, _DEBIT_KEYWORDS)
        credit_col = _find_col(headers, _CREDIT_KEYWORDS)
        currency_col = _find_col(headers, _CURRENCY_KEYWORDS)

        # Must have date + description + some amount column(s)
        if date_col is None or desc_col is None:
            continue
        if amount_col is None and debit_col is None and credit_col is None:
            continue

        # Parse data rows (skip separator at index 1)
        for row_line in table_lines[2:]:
            cells = [c.strip() for c in row_line.split("|")[1:-1]]
            if len(cells) < max(
                (c for c in (date_col, desc_col, amount_col,
                             debit_col, credit_col) if c is not None),
                default=0
            ) + 1:
                continue

            date_val = cells[date_col]
            # Skip bold summary/subtotal rows
            if date_val.startswith("**") or not date_val.strip():
                continue

            desc_val = cells[desc_col]

            # Calculate amount
            try:
                if amount_col is not None:
                    amt = _clean_amount(cells[amount_col])
                else:
                    d = _clean_amount(
                        cells[debit_col] if debit_col is not None else "0")
                    c = _clean_amount(
                        cells[credit_col] if credit_col is not None else "0")
                    amt = c - d
            except (ValueError, IndexError):
                continue

            if amt == 0:
                continue

            if is_cc:
                amt = -amt

            currency = "TWD"
            if currency_col is not None and currency_col < len(cells):
                cur = cells[currency_col].strip()
                if cur:
                    currency = _normalize_currency(cur)

            cat = ""
            if category_rules:
                cat = _classify(desc_val, category_rules) or ""

            transactions.append({
                "date": _normalize_date(date_val),
                "description": desc_val,
                "amount": amt,
                "currency": currency,
                "category": cat,
                "account": vendor,
            })

    return transactions


# ---------- CSV ----------

def parse_csv(path, category_rules=None):
    """Parse a standard CSV file into transactions list.

    Expected columns: date, description, amount
    Optional columns: currency, category, account
    """
    content = _try_read(path)
    reader = csv.DictReader(io.StringIO(content))

    transactions = []
    for i, row in enumerate(reader, start=2):
        # Require at least date + description + amount
        if "date" not in row or "amount" not in row:
            continue

        amt = _clean_amount(row.get("amount", 0))
        if amt == 0:
            continue

        cat = row.get("category", "").strip()
        if not cat and category_rules:
            cat = _classify(row.get("description", ""), category_rules) or ""

        transactions.append({
            "date": row["date"].strip(),
            "description": row.get("description", "").strip(),
            "amount": amt,
            "currency": row.get("currency", "TWD").strip().upper() or "TWD",
            "category": cat,
            "account": row.get("account", "").strip(),
        })

    return transactions


def parse_assets_csv(path):
    """Parse assets CSV. Columns: account, category, amount, currency."""
    content = _try_read(path)
    reader = csv.DictReader(io.StringIO(content))

    assets = []
    for row in reader:
        amt = _clean_amount(row.get("amount", 0))
        if amt == 0:
            continue
        assets.append({
            "name": row.get("account", row.get("name", "Unknown")).strip(),
            "category": row.get("category", "Unknown").strip(),
            "amount": amt,
            "currency": row.get("currency", "TWD").strip().upper() or "TWD",
        })
    return assets


# ---------- Markdown + JSON (doc-cleaner pipeline) ----------

def _extract_json_from_md(content):
    """Extract STRUCTURED_DATA JSON block from markdown content."""
    marker = "STRUCTURED_DATA_START"
    if marker not in content:
        return None
    start = content.find(marker) + len(marker)
    end = content.find("STRUCTURED_DATA_END", start)
    if end == -1:
        end = len(content)
    json_str = content[start:end].strip()
    # Strip markdown code fence if present
    if json_str.startswith("```"):
        json_str = json_str.split("\n", 1)[-1]
    if json_str.endswith("```"):
        json_str = json_str.rsplit("```", 1)[0]
    return json.loads(json_str)


def parse_single_md(path, category_rules=None):
    """Parse a single Markdown file with STRUCTURED_DATA.

    Returns (transactions, assets).
    Raises json.JSONDecodeError if JSON is malformed.

    Fallback: when transactions[]/assets[] are absent but refined_markdown
    exists, extracts transactions from pipe tables in the markdown.
    """
    p = Path(path)
    content = _try_read(p)
    data = _extract_json_from_md(content)
    if not data or not isinstance(data, dict):
        return [], []

    # Basic schema check
    tx_raw = data.get("transactions", [])
    assets_raw = data.get("assets", [])
    if not isinstance(tx_raw, list):
        tx_raw = []
    if not isinstance(assets_raw, list):
        assets_raw = []

    vendor = data.get("vendor", p.stem)
    is_cc = "信用卡" in p.name or "credit" in vendor.lower()

    # --- Primary path: pre-structured transactions/assets ---
    transactions = []
    for t in tx_raw:
        amt = _clean_amount(t.get("amount", 0))
        if is_cc:
            amt = -amt

        cat = t.get("category", "")
        if not cat and category_rules:
            cat = _classify(t.get("description", ""), category_rules) or ""

        transactions.append({
            "date": t.get("date", ""),
            "description": t.get("description", ""),
            "amount": amt,
            "currency": t.get("currency", "TWD"),
            "category": cat,
            "account": vendor,
        })

    assets = []
    for a in assets_raw:
        assets.append({
            "name": a.get("name", "Unknown"),
            "category": a.get("category", "Unknown"),
            "amount": _clean_amount(a.get("amount", 0)),
            "currency": a.get("currency", "TWD"),
            "vendor": vendor,
        })

    # --- Fallback: extract from refined_markdown pipe tables ---
    if not transactions and not assets:
        md_text = data.get("refined_markdown", "")
        if md_text:
            transactions = _parse_tables_from_markdown(
                md_text, is_cc=is_cc, vendor=vendor,
                category_rules=category_rules,
            )
            if transactions:
                print(f"  NOTE: {p.name}: extracted {len(transactions)} "
                      f"transactions from pipe tables (fallback mode)",
                      file=sys.stderr)
            if not transactions:
                print(f"  WARNING: {p.name}: no transactions or assets found "
                      f"in STRUCTURED_DATA or pipe tables", file=sys.stderr)

    return transactions, assets


def parse_markdown_dir(dir_path, prefix=None, category_rules=None):
    """Scan directory for Markdown files with STRUCTURED_DATA.

    Returns (all_transactions, all_assets, vendors).
    """
    dir_path = Path(dir_path)
    all_tx = []
    all_assets = []
    vendors = set()

    for md_file in sorted(dir_path.glob("*.md")):
        if prefix and not md_file.name.startswith(prefix):
            continue
        try:
            tx, assets = parse_single_md(md_file, category_rules=category_rules)
        except json.JSONDecodeError as e:
            import sys
            print(f"  WARNING: Invalid JSON in {md_file.name}: {e}", file=sys.stderr)
            continue
        except Exception:
            continue
        if not tx and not assets:
            continue

        all_tx.extend(tx)
        all_assets.extend(assets)
        # Extract vendor from first tx or asset
        if tx:
            vendors.add(tx[0]["account"])
        elif assets:
            vendors.add(assets[0].get("vendor", md_file.stem))

    return all_tx, all_assets, vendors

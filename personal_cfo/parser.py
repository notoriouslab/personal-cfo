"""Parse financial data from CSV or Markdown+JSON (doc-cleaner output).

Supports three input modes:
1. CSV — universal, user-provided
2. Markdown with transactions[]/assets[] JSON — pre-structured
3. Markdown with refined_markdown only — fallback, extracts from pipe tables
"""

import csv
import json
import io
import math
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
_REMARKS_KEYWORDS = ("備註", "附註", "memo", "remarks")


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
        remarks_col = _find_col(headers, _REMARKS_KEYWORDS)

        # Must have date + description + some amount column(s)
        if date_col is None or desc_col is None:
            continue
        if amount_col is None and debit_col is None and credit_col is None:
            continue

        # Parse data rows (skip separator at index 1)
        for row_line in table_lines[2:]:
            cells = [c.strip() for c in row_line.split("|")[1:-1]]
            required_cols = [c for c in (date_col, desc_col, amount_col,
                                         debit_col, credit_col)
                             if c is not None]
            if len(cells) < max(required_cols) + 1:
                continue

            date_val = cells[date_col]
            # Skip bold summary/subtotal rows
            if date_val.startswith("**") or not date_val.strip():
                continue

            desc_val = cells[desc_col]

            # Merge remarks column into description so keyword-based
            # category rules can match on remark text (e.g. "轉出123456")
            if remarks_col is not None and remarks_col < len(cells):
                remark = cells[remarks_col].strip()
                if remark and remark not in desc_val:
                    desc_val = f"{desc_val} {remark}"

            # Calculate amount — prefer debit/credit split over generic
            # amount_col (headers like "支出金額"/"存入金額" both contain
            # "金額", causing amount_col to match the wrong column)
            try:
                if debit_col is not None or credit_col is not None:
                    d = _clean_amount(
                        cells[debit_col] if debit_col is not None else "0")
                    c = _clean_amount(
                        cells[credit_col] if credit_col is not None else "0")
                    amt = c - d
                elif amount_col is not None:
                    amt = _clean_amount(cells[amount_col])
                else:
                    continue
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


# ---------- Asset extraction from pipe tables ----------

_BALANCE_KEYWORDS = ("帳戶餘額", "存款餘額", "餘額", "balance", "約當台幣",
                     "約當新臺幣", "貸款餘額", "參考市値", "參考市值",
                     "存單面額", "面額")
_ACCT_TYPE_KEYWORDS = ("帳號類別", "帳戶種類", "帳戶類別", "存款種類", "貸款種類",
                       "項目", "account type", "證券", "交易別")
_ORIG_BAL_KEYWORDS = ("帳戶餘額(原幣)", "餘額(原幣)", "原幣", "總投資成本")

_ACCT_CATEGORY_MAP = {
    "活存": "Cash", "活期": "Cash", "checking": "Cash",
    "組合存款": "Cash", "儲蓄存款": "Cash", "外幣存款": "Cash",
    "定存": "Fixed Deposit", "定期": "Fixed Deposit",
    "基金": "Fund", "信託": "Fund", "投資型信託": "Fund",
    "連動債": "Structured Note", "結構型": "Structured Product",
    "債券": "Bond", "海外債券": "Bond",
    "黃金": "other", "保險": "insurance_value",
    "現股": "Equity", "融資": "Equity", "融券": "Equity",
    "ETF": "Equity", "股票": "Equity",
}

_SECURITIES_KEYWORDS = ("參考市値", "參考市值", "庫存餘額", "總投資成本")


def _infer_asset_category(acct_type):
    """Map account type string to asset category.

    Returns "other" for unrecognized types. Callers in deposit-table context
    (where "other" is unlikely) can override if needed.
    """
    for kw, cat in _ACCT_CATEGORY_MAP.items():
        if kw in acct_type:
            return cat
    return "other"


def _parse_assets_from_tables(md_text, vendor=""):
    """Extract assets from account summary pipe tables.

    Identifies asset tables by: has balance column but NOT debit/credit columns.
    Skips totals/subtotals to avoid double-counting.
    """
    assets = []
    lines = md_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line.startswith("|"):
            i += 1
            continue

        table_lines = []
        while i < len(lines) and lines[i].strip().startswith("|"):
            table_lines.append(lines[i].strip())
            i += 1

        if len(table_lines) < 3:
            continue

        headers = [h.strip() for h in table_lines[0].split("|")[1:-1]]

        # Must have balance column
        bal_col = _find_col(headers, _BALANCE_KEYWORDS)
        if bal_col is None:
            continue

        # Must NOT have debit/credit columns (those are transaction tables)
        if (_find_col(headers, _DEBIT_KEYWORDS) is not None
                or _find_col(headers, _CREDIT_KEYWORDS) is not None):
            continue

        acct_col = _find_col(headers, _ACCT_TYPE_KEYWORDS)
        currency_col = _find_col(headers, _CURRENCY_KEYWORDS)
        orig_bal_col = _find_col(headers, _ORIG_BAL_KEYWORDS)

        # Detect loan table
        is_loan_table = any("貸款" in h for h in headers)

        # Detect securities/stock holdings table
        is_securities = any(kw in h for h in headers
                           for kw in _SECURITIES_KEYWORDS)
        sec_name_col = None
        sec_mktval_col = None
        if is_securities:
            for ci, h in enumerate(headers):
                if "證券" in h and "證交" not in h:
                    sec_name_col = ci
                if "參考市値" in h or "參考市值" in h:
                    sec_mktval_col = ci
            if sec_mktval_col is not None:
                bal_col = sec_mktval_col

        # Detect overview/summary tables (約當台幣/約當新臺幣)
        is_overview = any("約當台幣" in h or "約當新臺幣" in h
                         or "資產分配" in h for h in headers)
        if is_overview:
            for ci, h in enumerate(headers):
                if "約當台幣" in h or "約當新臺幣" in h:
                    bal_col = ci
                    break

        for row_line in table_lines[2:]:
            cells = [c.strip() for c in row_line.split("|")[1:-1]]
            if len(cells) <= bal_col:
                continue

            # For securities tables: prefer 「證券」column as name (e.g. "0050 元大台灣50").
            # Fallback to 「交易別」column (acct_col) if no dedicated name column
            # — in that case acct_type may be "現股" instead of stock name, which is
            # still usable for _infer_asset_category but less descriptive.
            if is_securities and sec_name_col is not None:
                acct_type = (cells[sec_name_col].strip().replace("**", "")
                             if sec_name_col < len(cells) else "")
            else:
                acct_type = (cells[acct_col].strip().replace("**", "")
                             if acct_col is not None
                             and acct_col < len(cells) else "")

            # Skip totals, subtotals, separator rows, group headers
            if not acct_type or acct_type.startswith("---"):
                continue
            if any(kw in acct_type for kw in ("合計", "小計", "資產合計",
                                               "貸款合計")):
                continue
            if any(kw in acct_type for kw in ("存款產品", "投資產品",
                                               "存款與投資總額")):
                continue
            if "無交易" in acct_type:
                continue

            # In overview tables, skip deposit items (avoid double-counting
            # with detail deposit tables). Use category inference as primary
            # check, plus keyword fallback for edge cases like "儲蓄", "外幣帳戶".
            if is_overview:
                inferred = _infer_asset_category(acct_type)
                if inferred in ("Cash", "Fixed Deposit"):
                    continue
                if any(kw in acct_type for kw in (
                        "存款帳戶", "台幣存款", "外幣存款", "存款",
                        "儲蓄", "外幣帳戶")):
                    continue

            try:
                bal = _clean_amount(cells[bal_col])
            except (ValueError, IndexError):
                continue
            if bal == 0:
                continue

            currency = "TWD"
            if currency_col is not None and currency_col < len(cells):
                cur = cells[currency_col].strip()
                if cur:
                    currency = _normalize_currency(cur)

            # For foreign currency, use original balance if available
            amount = bal
            if (not is_overview and orig_bal_col is not None
                    and orig_bal_col < len(cells) and currency != "TWD"):
                try:
                    orig = _clean_amount(cells[orig_bal_col])
                    if orig > 0:
                        amount = orig
                except (ValueError, IndexError):
                    pass

            # Determine category
            if is_securities:
                tx_type = ""
                if acct_col is not None and acct_col < len(cells):
                    tx_type = cells[acct_col].strip()
                category = (_infer_asset_category(tx_type) if tx_type
                           else "Equity")
                if category == "Cash":
                    category = "Equity"
            elif is_loan_table or "貸款" in acct_type or "房貸" in acct_type:
                category = "Loan"
                amount = -abs(amount)
            else:
                category = _infer_asset_category(acct_type)

            assets.append({
                "name": acct_type,
                "category": category,
                "amount": amount,
                "currency": currency,
                "vendor": vendor,
            })

    return assets


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
    is_cc = "信用卡" in p.name or "credit" in p.name.lower()

    data = _extract_json_from_md(content)

    # --- No STRUCTURED_DATA: try plain pipe tables directly ---
    if not data or not isinstance(data, dict):
        transactions = _parse_tables_from_markdown(
            content, is_cc=is_cc, vendor=p.stem,
            category_rules=category_rules,
        )
        assets = _parse_assets_from_tables(content, vendor=p.stem)
        if transactions:
            print(f"  NOTE: {p.name}: extracted {len(transactions)} "
                  f"transactions from pipe tables (plain markdown)",
                  file=sys.stderr)
        if assets:
            print(f"  NOTE: {p.name}: extracted {len(assets)} "
                  f"assets from account summary tables",
                  file=sys.stderr)
        return transactions, assets

    # Basic schema check
    tx_raw = data.get("transactions", [])
    assets_raw = data.get("assets", [])
    if not isinstance(tx_raw, list):
        tx_raw = []
    if not isinstance(assets_raw, list):
        assets_raw = []

    vendor = data.get("vendor", p.stem)
    if not is_cc:
        is_cc = "credit" in vendor.lower()

    # Infer default currency from assets: if ALL assets share a single
    # non-TWD currency, use that as default for transactions too.
    # Covers sub-brokerage (複委託) where assets are all USD but
    # transaction JSON lacks currency field.
    _asset_currencies = {a.get("currency", "").upper()
                         for a in assets_raw if a.get("currency")}
    _asset_currencies.discard("")
    inferred_currency = None
    if len(_asset_currencies) == 1:
        only_cur = _asset_currencies.pop()
        if only_cur != "TWD":
            inferred_currency = only_cur

    # --- Primary path: pre-structured transactions/assets ---
    transactions = []
    for t in tx_raw:
        amt = _clean_amount(t.get("amount", 0))
        if is_cc:
            amt = -amt

        # User category_rules always override AI-assigned categories
        cat = ""
        if category_rules:
            cat = _classify(t.get("description", ""), category_rules) or ""
        if not cat:
            cat = t.get("category", "")

        # Detect currency: explicit field > description hint > inferred > TWD
        currency = t.get("currency", "")
        if not currency or currency == "TWD":
            detected = _detect_currency_from_desc(t.get("description", ""))
            if detected:
                currency = detected
            elif inferred_currency:
                currency = inferred_currency
        if not currency:
            currency = "TWD"

        transactions.append({
            "date": t.get("date", ""),
            "description": t.get("description", ""),
            "amount": amt,
            "currency": currency,
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

    # --- Supplement / Fallback: cross-check with refined_markdown ---
    # AI-generated JSON may be incomplete (missing transactions).
    # Always parse pipe tables from refined_markdown and supplement any
    # transactions not already captured in JSON.
    md_text = data.get("refined_markdown", "")
    if md_text:
        pipe_tx = _parse_tables_from_markdown(
            md_text, is_cc=is_cc, vendor=vendor,
            category_rules=category_rules,
        )
        if pipe_tx:
            if not transactions and not assets:
                # Full fallback: no JSON data at all
                transactions = pipe_tx
                print(f"  NOTE: {p.name}: extracted {len(pipe_tx)} "
                      f"transactions from pipe tables (fallback mode)",
                      file=sys.stderr)
            elif transactions:
                # Cross-reference: supplement missing + enrich descriptions
                json_by_sig = {}
                for idx, t in enumerate(transactions):
                    sig = (_normalize_date(t["date"]),
                           round(abs(t["amount"])))
                    json_by_sig[sig] = idx

                supplemented = 0
                enriched = 0
                for pt in pipe_tx:
                    sig = (_normalize_date(pt["date"]),
                           round(abs(pt["amount"])))
                    if sig not in json_by_sig:
                        # Missing from JSON — add it
                        transactions.append(pt)
                        json_by_sig[sig] = len(transactions) - 1
                        supplemented += 1
                    else:
                        # Exists in JSON — enrich if pipe table has
                        # a better description for classification
                        idx = json_by_sig[sig]
                        if (pt["description"] != transactions[idx][
                                "description"] and category_rules):
                            new_cat = _classify(
                                pt["description"], category_rules)
                            old_cat = transactions[idx]["category"]
                            if new_cat and new_cat != old_cat and (
                                    old_cat in ("", "internal_transfer")):
                                transactions[idx]["description"] = \
                                    pt["description"]
                                transactions[idx]["category"] = new_cat
                                enriched += 1

                if supplemented > 0 or enriched > 0:
                    print(f"  NOTE: {p.name}: pipe table cross-ref: "
                          f"+{supplemented} new, "
                          f"~{enriched} enriched "
                          f"(JSON had {len(transactions) - supplemented}, "
                          f"pipe tables had {len(pipe_tx)})",
                          file=sys.stderr)
    elif not transactions and not assets:
        print(f"  WARNING: {p.name}: no transactions or assets found "
              f"in STRUCTURED_DATA or pipe tables", file=sys.stderr)

    # --- Asset fallback: extract from pipe tables if JSON had no assets ---
    if not assets and md_text:
        pipe_assets = _parse_assets_from_tables(md_text, vendor=vendor)
        if pipe_assets:
            assets = pipe_assets
            print(f"  NOTE: {p.name}: extracted {len(pipe_assets)} "
                  f"assets from pipe tables (asset fallback)",
                  file=sys.stderr)

    return transactions, assets


def _match_period(path, prefix, target_year, target_month):
    """Check if a file matches the target period.

    Tries (in order):
    1. Filename prefix (e.g. "202512" matches "202512 永豐信用卡.md")
    2. STRUCTURED_DATA year/month fields
    3. Frontmatter year/month fields (read from file header)
    """
    if prefix and path.name.startswith(prefix):
        return True
    if not target_year or not target_month:
        return not prefix  # no period filter = accept all

    # Quick check: read file and look for year/month in STRUCTURED_DATA or frontmatter
    try:
        content = _try_read(path)
    except ValueError:
        return False

    # Check STRUCTURED_DATA JSON
    try:
        data = _extract_json_from_md(content)
        if data and isinstance(data, dict):
            if (str(data.get("year", "")) == target_year
                    and str(data.get("month", "")).zfill(2) == target_month):
                return True
    except (json.JSONDecodeError, Exception):
        pass

    # Check YAML frontmatter (between --- delimiters)
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            fm = content[3:end]
            # Simple string matching (avoid yaml dependency here)
            y_match = re.search(r'^year:\s*["\']?(\d{4})', fm, re.MULTILINE)
            m_match = re.search(r'^month:\s*["\']?(\d{1,2})', fm, re.MULTILINE)
            if y_match and m_match:
                if (y_match.group(1) == target_year
                        and m_match.group(1).zfill(2) == target_month):
                    return True

    return False


def parse_markdown_dir(dir_path, prefix=None, category_rules=None):
    """Scan directory for Markdown files with STRUCTURED_DATA.

    Period matching: tries filename prefix first, then falls back to
    year/month fields in STRUCTURED_DATA or frontmatter. This handles
    files with non-standard naming like "台新銀行綜合對帳單 2025年12月份.md".

    Returns (all_transactions, all_assets, vendors).
    """
    dir_path = Path(dir_path)
    all_tx = []
    all_assets = []
    vendors = set()

    # Parse prefix into year/month for fallback matching
    target_year, target_month = None, None
    if prefix and len(prefix) >= 6:
        target_year = prefix[:4]
        target_month = prefix[4:6]

    for md_file in sorted(dir_path.glob("*.md")):
        if prefix and not _match_period(md_file, prefix,
                                        target_year, target_month):
            continue
        try:
            tx, assets = parse_single_md(md_file, category_rules=category_rules)
        except json.JSONDecodeError as e:
            print(f"  WARNING: Invalid JSON in {md_file.name}: {e}",
                  file=sys.stderr)
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

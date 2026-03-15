"""Pipe table extraction — transactions and assets from Markdown tables."""

from ..models import Transaction, Asset
from ._normalize import (
    _clean_amount, _classify, _normalize_currency, _normalize_date,
)


# Column header keywords for detection
_DATE_KEYWORDS = ("消費日", "交易日", "日期", "date")
_DESC_KEYWORDS = ("帳單說明", "說明", "摘要", "description")
_AMOUNT_KEYWORDS = ("臺幣金額", "台幣金額", "金額", "amount")
_DEBIT_KEYWORDS = ("支出",)
_CREDIT_KEYWORDS = ("存入",)
_CURRENCY_KEYWORDS = ("幣別",)
_REMARKS_KEYWORDS = ("備註", "附註", "memo", "remarks")

# Asset-specific keywords
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


def _find_col(headers, keywords):
    """Find first column index whose header contains any keyword."""
    for i, h in enumerate(headers):
        h_clean = h.strip().replace("**", "").lower()
        for kw in keywords:
            if kw.lower() in h_clean:
                return i
    return None


def _infer_asset_category(acct_type):
    """Map account type string to asset category.

    Returns "other" for unrecognized types. Callers in deposit-table context
    (where "other" is unlikely) can override if needed.
    """
    for kw, cat in _ACCT_CATEGORY_MAP.items():
        if kw in acct_type:
            return cat
    return "other"


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

            transactions.append(Transaction(
                date=_normalize_date(date_val),
                description=desc_val,
                amount=amt,
                currency=currency,
                category=cat,
                account=vendor,
            ))

    return transactions


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

            assets.append(Asset(
                name=acct_type,
                category=category,
                amount=amount,
                currency=currency,
                vendor=vendor,
            ))

    return assets

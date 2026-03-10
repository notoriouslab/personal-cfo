"""Deterministic accounting engine — 8-bucket Income Statement + Balance Sheet + Cash Flow."""


# Asset category → accounting group mapping
_ASSET_GROUP = {
    "Cash": "liquid_cash", "Deposit": "liquid_cash", "Savings": "liquid_cash",
    "Fixed Deposit": "liquid_cash", "liquid_cash": "liquid_cash",
    "Stock": "equities", "ETF": "equities", "Equity": "equities",
    "Fund": "equities", "equities": "equities",
    "Bond": "bonds", "Structured Note": "bonds", "Structured Product": "bonds",
    "Investment": "bonds", "bonds": "bonds",
    "Insurance": "insurance", "insurance_value": "insurance",
    "Real Estate": "real_estate", "real_estate": "real_estate",
    "Loan": "liabilities", "Mortgage": "liabilities", "Liability": "liabilities",
    "Credit": "liabilities", "Credit Card": "liabilities",
    "mortgage": "liabilities", "loan": "liabilities", "credit_card": "liabilities",
}

# IS bucket labels
IS_CAPITAL = "投資/資本轉移 (Capital Transfer)"
IS_SALARY = "經常性收入 (Salary/Income)"
IS_INVEST_INCOME = "投資收益 (Dividend/Interest)"
IS_CAPEX = "資本支出 (CapEx)"
IS_PRINCIPAL = "債務還本 (Principal)"
IS_INTEREST = "利息支出 (Interest)"
IS_FEES = "摩擦成本 (Fees)"
IS_LIVING = "生活與其他 (Living/Other)"

_IS_KEYS = [IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL, IS_LIVING,
            IS_CAPEX, IS_PRINCIPAL, IS_INTEREST, IS_FEES]


def _classify_tx(desc, cat, amount):
    """Classify a single transaction into an IS bucket."""
    dl = desc.lower()
    cl = cat.lower()

    # Fees
    if "手續費" in dl or "fee" in cl:
        return IS_FEES

    # Internal transfer — exclude from IS
    if cl == "internal_transfer" or "internal_transfer" in cl:
        return None

    if amount > 0:
        # Inflows — conservative: only classify what we're sure about
        if cl in ("salary", "income") or "薪" in dl:
            return IS_SALARY
        if cl in ("dividend", "interest", "interest_income") or "息" in dl or "股利" in dl:
            return IS_INVEST_INCOME
        # Only clearly investment-related keywords → capital transfer
        if any(k in dl for k in ("交割", "申購", "贖回", "信託")):
            return IS_CAPITAL
        if "investment" in cl:
            return IS_CAPITAL
        # Everything else (including ambiguous transfers) → Living
        # Users should set category_rules for precise classification
        return IS_LIVING
    else:
        # Outflows
        if cl == "housing" or any(k in dl for k in ("房貸", "貸款", "放款", "mortgage")):
            if "息" in dl or "interest" in cl:
                return IS_INTEREST
            return IS_PRINCIPAL  # principal repayment (not interest)
        if any(k in dl for k in ("裝潢", "修繕")):
            return IS_CAPEX
        if any(k in dl for k in ("交割", "申購", "買進", "投資", "信託")):
            return IS_CAPEX
        if "transfer" in cl or "轉帳" in dl or "轉出" in dl:
            return IS_CAPITAL
        if cl in ("insurance",) or "保險" in dl:
            return IS_LIVING
        return IS_LIVING


def compute_income_statement(transactions, to_twd):
    """Compute 8-bucket Income Statement from transactions.

    Returns dict of {bucket_name: total_twd}.
    """
    buckets = {k: 0.0 for k in _IS_KEYS}

    for t in transactions:
        amt = t["amount"]
        currency = t.get("currency", "TWD")
        amt_twd = to_twd(currency, amt)

        bucket = _classify_tx(t.get("description", ""), t.get("category", ""), amt)
        if bucket is None:
            continue  # internal_transfer, skip
        buckets[bucket] += amt_twd

    return buckets


def compute_balance_sheet(assets, manual_assets, to_twd):
    """Compute Balance Sheet from asset list + manual assets.

    Returns dict with:
        assets_by_group: {group: total_twd}
        liabilities: total_twd
        total_assets: twd
        total_liabilities: twd
        net_worth: twd
        total_cash: twd
        risk_buckets: {group: twd}
    """
    risk_buckets = {
        "liquid_cash": 0.0,
        "equities": 0.0,
        "bonds": 0.0,
        "real_estate": 0.0,
        "insurance": 0.0,
        "other": 0.0,
    }
    total_liabilities = 0.0
    details = []

    def _add_asset(name, category, amount, currency, vendor=""):
        val = to_twd(currency, amount)
        group = _ASSET_GROUP.get(category, "other")

        details.append({
            "name": name, "category": category, "group": group,
            "amount_twd": val, "currency": currency,
            "amount_orig": amount, "vendor": vendor,
        })

        if group == "liabilities":
            nonlocal total_liabilities
            total_liabilities += abs(val)
        else:
            risk_buckets[group] = risk_buckets.get(group, 0.0) + val

    # From parsed assets
    for a in assets:
        _add_asset(
            a.get("name", "Unknown"),
            a.get("category", "Unknown"),
            a["amount"],
            a.get("currency", "TWD"),
            a.get("vendor", ""),
        )

    # From manual_assets in config
    for ma in manual_assets:
        _add_asset(
            ma.get("name", "Manual"),
            ma.get("category", "other_asset"),
            ma["amount"],
            ma.get("currency", "TWD"),
            "config",
        )

    total_assets = sum(risk_buckets.values())
    net_worth = total_assets - total_liabilities

    return {
        "details": details,
        "risk_buckets": risk_buckets,
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": net_worth,
        "total_cash": risk_buckets["liquid_cash"],
    }


def compute_cash_flow(is_buckets):
    """Derive operating cash flow from IS buckets.

    Excludes IS_CAPITAL (asset transfers between accounts) and IS_CAPEX
    (investment purchases) since these are asset swaps, not real income/expense.

    Returns dict with inflow, outflow, net_flow.
    """
    # Exclude capital transfers and investment purchases from cash flow
    excluded = {IS_CAPITAL, IS_CAPEX}
    inflow = 0.0
    outflow = 0.0

    for bucket, val in is_buckets.items():
        if bucket in excluded:
            continue
        if val > 0:
            inflow += val
        else:
            outflow += val  # negative

    return {
        "inflow": inflow,
        "outflow": outflow,
        "net_flow": inflow + outflow,
    }

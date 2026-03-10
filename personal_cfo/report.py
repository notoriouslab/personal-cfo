"""Markdown report renderer for financial statements."""

from .accounting import (
    IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL, IS_LIVING,
    IS_CAPEX, IS_PRINCIPAL, IS_INTEREST, IS_FEES,
)


def _fmt(amount):
    """Format number with thousand separators."""
    return f"{amount:,.0f}"


def _pct(ratio):
    """Format ratio as percentage."""
    return f"{ratio * 100:.1f}%"


def render_cfo_report(period, is_buckets, bs, cash_flow, market, glide, cfg):
    """Render full CFO Markdown report.

    Args:
        period: e.g. "2026-01"
        is_buckets: dict from compute_income_statement
        bs: dict from compute_balance_sheet
        cash_flow: dict from compute_cash_flow
        market: dict from fetch_market_anchors
        glide: dict from diagnose_drift (or None)
        cfg: config dict
    """
    base = cfg["assumptions"]["base_currency"]
    lines = [f"# Financial Report — {period}\n"]

    # ---------- Income Statement ----------
    lines.append("## Income Statement (損益表)\n")
    lines.append(f"| Category | Amount ({base}) |")
    lines.append("|----------|----------:|")

    # Revenue
    for bucket in [IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL]:
        val = is_buckets.get(bucket, 0)
        if val != 0:
            lines.append(f"| {bucket} | {_fmt(val)} |")

    # Expenses
    for bucket in [IS_LIVING, IS_CAPEX, IS_PRINCIPAL, IS_INTEREST, IS_FEES]:
        val = is_buckets.get(bucket, 0)
        if val != 0:
            lines.append(f"| {bucket} | {_fmt(val)} |")

    net_operating = sum(is_buckets.values())
    lines.append(f"| **Net Operating (營運淨利)** | **{_fmt(net_operating)}** |")
    lines.append("")

    # ---------- Balance Sheet ----------
    if bs and bs["total_assets"] > 0:
        lines.append("## Balance Sheet (資產負債表)\n")
        lines.append(f"| Category | Amount ({base}) |")
        lines.append("|----------|----------:|")

        rb = bs["risk_buckets"]
        group_labels = {
            "liquid_cash": "流動資產 (Cash)",
            "equities": "股票/ETF (Equities)",
            "bonds": "債券/結構型商品 (Bonds)",
            "real_estate": "不動產 (Real Estate)",
            "insurance": "保險價值 (Insurance)",
            "other": "其他 (Other)",
        }
        for group, label in group_labels.items():
            val = rb.get(group, 0)
            if val != 0:
                lines.append(f"| {label} | {_fmt(val)} |")

        lines.append(f"| **Total Assets (資產合計)** | **{_fmt(bs['total_assets'])}** |")

        if bs["total_liabilities"] > 0:
            lines.append(f"| Liabilities (負債) | -{_fmt(bs['total_liabilities'])} |")

        lines.append(f"| **Net Worth (淨資產)** | **{_fmt(bs['net_worth'])}** |")
        lines.append("")

        # Key ratios
        liability_ratio = bs["total_liabilities"] / bs["total_assets"] if bs["total_assets"] else 0
        monthly_exp = cfg["assumptions"].get("monthly_expense", 100000)
        emergency_months = bs["total_cash"] / monthly_exp if monthly_exp else 0

        lines.append("### Key Ratios\n")
        lines.append(f"- Liability Ratio (負債比): {_pct(liability_ratio)}")
        lines.append(f"- Emergency Fund (緊急預備金): {emergency_months:.1f} months")

        if liability_ratio > 0.6:
            lines.append(f"- ⚠ WARNING: Liability ratio exceeds 60%")
        lines.append("")

    # ---------- Cash Flow ----------
    lines.append("## Cash Flow (現金流量)\n")
    lines.append(f"| | Amount ({base}) |")
    lines.append("|--|----------:|")
    lines.append(f"| Inflow (流入) | {_fmt(cash_flow['inflow'])} |")
    lines.append(f"| Outflow (流出) | {_fmt(cash_flow['outflow'])} |")
    lines.append(f"| **Net Flow (淨流量)** | **{_fmt(cash_flow['net_flow'])}** |")
    lines.append("")

    # ---------- Market Anchors ----------
    if market:
        lines.append("## Market Anchors (市場定錨)\n")
        lines.append("| Indicator | Value |")
        lines.append("|-----------|------:|")
        labels = {
            "US_10Y_Yield": "US 10Y Yield",
            "BTC_USD": "BTC/USD",
            "Gold": "Gold Futures",
            "USD_TWD": "USD/TWD",
            "TAIEX": "TAIEX",
        }
        for key, label in labels.items():
            val = market.get(key)
            if val is not None:
                if "Yield" in label:
                    lines.append(f"| {label} | {val:.2f}% |")
                else:
                    lines.append(f"| {label} | {_fmt(val)} |")
        lines.append("")

    # ---------- Glide Path ----------
    if glide:
        lines.append("## Retirement Glide Path (退休軌道)\n")
        status_icon = {"on_track": "🟢", "minor_drift": "🟡", "major_drift": "🔴"}.get(glide["status"], "⚪")
        lines.append(f"- Age (年齡): {glide['age']}")
        lines.append(f"- Target Equity Ratio (目標股票比): {_pct(glide['target'])}")
        lines.append(f"- Actual Equity Ratio (實際股票比): {_pct(glide['actual'])}")
        lines.append(f"- Drift (偏移): {glide['drift']:+.1%}")
        lines.append(f"- Status: {status_icon} **{glide['status'].upper()}**")
        lines.append(f"- {glide['message']}")
        lines.append("")

    return "\n".join(lines)


def render_track_report(snapshots, glide, cfg):
    """Render Track mode report from snapshot history.

    Args:
        snapshots: list of snapshot dicts (sorted by period)
        glide: dict from diagnose_drift
        cfg: config dict
    """
    lines = ["# Track Audit — Retirement Glide Path\n"]

    # Current diagnosis
    if glide:
        status_icon = {"on_track": "🟢", "minor_drift": "🟡", "major_drift": "🔴"}.get(glide["status"], "⚪")
        lines.append("## Current Diagnosis\n")
        lines.append(f"- Age: {glide['age']}")
        lines.append(f"- Target Equity: {_pct(glide['target'])}")
        lines.append(f"- Actual Equity: {_pct(glide['actual'])}")
        lines.append(f"- Drift: {glide['drift']:+.1%} → {status_icon} **{glide['status'].upper()}**")
        lines.append(f"- {glide['message']}")
        lines.append("")

    # Trend table
    if len(snapshots) >= 2:
        lines.append("## Trend (趨勢)\n")
        lines.append("| Period | Net Worth | Equity Ratio | Status |")
        lines.append("|--------|----------:|:------------:|--------|")
        for s in snapshots[-6:]:  # last 6 periods
            nw = _fmt(s.get("net_worth", 0))
            er = _pct(s.get("equity_ratio", 0))
            st = s.get("glide_path", {}).get("status", "—")
            lines.append(f"| {s['period']} | {nw} | {er} | {st} |")
        lines.append("")

    # Glide path table
    from .glide_path import glide_path_table
    table = glide_path_table(cfg)
    if table:
        lines.append("## Glide Path Table (滑行路徑)\n")
        lines.append("| Age | Target Equity |")
        lines.append("|----:|--------------:|")
        for age, target in table:
            marker = " ← now" if age == glide["age"] else ""
            lines.append(f"| {age} | {_pct(target)}{marker} |")
        lines.append("")

    return "\n".join(lines)

"""Markdown report renderer for financial statements."""

from .accounting import (
    IS_SALARY, IS_INVEST_INCOME, IS_CAPITAL, IS_LIVING,
    IS_CAPEX, IS_PRINCIPAL, IS_INTEREST, IS_FEES,
)
from .models import BalanceSheet, CashFlow, ClassifiedTx, GlideDiagnosis

# Confidence markers for data sources
C_HARD = "🔵"   # hard data — from bank statements
C_EST  = "🟡"   # estimated — market prices, FX rates
C_ASSU = "⚪"   # assumption — inflation, manual input

# Operating buckets (real income/expense that affect savings)
_OP_REVENUE = [IS_SALARY, IS_INVEST_INCOME]
_OP_EXPENSE = [IS_LIVING, IS_PRINCIPAL, IS_INTEREST, IS_FEES]

# Capital activity buckets (asset swaps, not real income/expense)
_CAP_BUCKETS = [IS_CAPITAL, IS_CAPEX]


def _fmt(amount):
    """Format number with thousand separators."""
    return f"{amount:,.0f}"


def _pct(ratio):
    """Format ratio as percentage."""
    return f"{ratio * 100:.1f}%"


def _savings_rate(is_buckets):
    """Calculate savings rate from operating income vs expense.

    Uses operating revenue (salary + investment income) as denominator,
    NOT cash flow inflow, to avoid extreme percentages when capital
    transfers dominate.

    Returns 0 (displayed as N/A) when operating revenue is insufficient
    to produce a meaningful savings rate.
    """
    op_revenue = sum(is_buckets.get(b, 0) for b in _OP_REVENUE)
    if op_revenue <= 0:
        return 0
    op_expense = sum(is_buckets.get(b, 0) for b in _OP_EXPENSE)  # negative
    rate = (op_revenue + op_expense) / op_revenue
    if rate < -1.0:
        return 0  # expense far exceeds revenue, rate is meaningless
    return rate


def _render_bucket_detail(classified_tx, bucket, max_items=10):
    """Render transaction detail lines for a single IS bucket."""
    items = [t for t in classified_tx if t.bucket == bucket]
    if not items:
        return []

    lines = []
    # Sort by absolute amount descending
    items.sort(key=lambda t: abs(t.amount_twd), reverse=True)
    shown = items[:max_items]

    for t in shown:
        desc = t.description[:30]
        amt = _fmt(t.amount_twd)
        cur = t.currency
        # Only show currency note if foreign AND not already in description
        if cur != "TWD" and f"({cur})" not in t.description:
            cur_note = f" ({cur})"
        else:
            cur_note = ""
        lines.append(f"|   ↳ {desc}{cur_note} | {amt} | |")

    if len(items) > max_items:
        rest_count = len(items) - max_items
        rest_total = sum(t.amount_twd for t in items[max_items:])
        lines.append(f"|   ↳ ...其他 {rest_count} 筆 | {_fmt(rest_total)} | |")

    return lines


def render_cfo_report(period, is_buckets, bs, cash_flow, market, glide, cfg,
                      classified_tx=None, warnings=None):
    """Render full CFO Markdown report."""
    base = cfg["assumptions"]["base_currency"]

    # --- Compute operating net income (excludes capital activity) ---
    op_revenue = sum(is_buckets.get(b, 0) for b in _OP_REVENUE)
    op_expense = sum(is_buckets.get(b, 0) for b in _OP_EXPENSE)
    op_net = op_revenue + op_expense
    cap_net = sum(is_buckets.get(b, 0) for b in _CAP_BUCKETS)

    # --- Executive Summary ---
    nw_str = f"NT${_fmt(bs.net_worth)}" if bs else "—"
    sr = _savings_rate(is_buckets)
    sr_str = _pct(sr) if sr != 0 else "N/A"
    glide_str = ""
    if glide:
        icon = {"on_track": "🟢", "minor_drift": "🟡", "major_drift": "🔴"}.get(glide.status, "⚪")
        _status_zh = {"on_track": "正常", "minor_drift": "輕微偏移", "major_drift": "重大偏移"}
        glide_str = f" | 退休軌道 {icon} {_status_zh.get(glide.status, glide.status)}"

    lines = [f"# 財務報告 — {period}\n"]
    lines.append(f"> 經常性淨利 **NT${_fmt(op_net)}** | "
                 f"淨資產 **{nw_str}** | "
                 f"儲蓄率 **{sr_str}**"
                 f"{glide_str}\n")
    lines.append(f"> {C_HARD} 對帳單數據 "
                 f"{C_EST} 市場估值 "
                 f"{C_ASSU} 假設值\n")
    lines.append("---\n")

    # --- Income Statement: Operating Section ---
    lines.append("## 損益表\n")
    lines.append("### 經常性損益\n")
    lines.append(f"| 項目 | 金額 ({base}) | |")
    lines.append("|------|----------:|:--:|")

    for bucket in _OP_REVENUE:
        val = is_buckets.get(bucket, 0)
        if val != 0:
            lines.append(f"| {bucket} | {_fmt(val)} | {C_HARD} |")
            if classified_tx:
                lines.extend(_render_bucket_detail(classified_tx, bucket))
    lines.append(f"| *經常性收入小計* | *{_fmt(op_revenue)}* | |")

    for bucket in _OP_EXPENSE:
        val = is_buckets.get(bucket, 0)
        if val != 0:
            lines.append(f"| {bucket} | {_fmt(val)} | {C_HARD} |")
            if classified_tx:
                lines.extend(_render_bucket_detail(classified_tx, bucket))
    lines.append(f"| *經常性支出小計* | *{_fmt(op_expense)}* | |")

    lines.append(f"| **經常性淨利** | **{_fmt(op_net)}** | |")
    lines.append("")

    # --- Income Statement: Capital Activity Section ---
    if any(is_buckets.get(b, 0) != 0 for b in _CAP_BUCKETS):
        lines.append("### 資本活動 (不計入經常性損益)\n")
        lines.append(f"| 項目 | 金額 ({base}) | |")
        lines.append("|------|----------:|:--:|")
        for bucket in _CAP_BUCKETS:
            val = is_buckets.get(bucket, 0)
            if val != 0:
                lines.append(f"| {bucket} | {_fmt(val)} | {C_HARD} |")
                if classified_tx:
                    lines.extend(_render_bucket_detail(classified_tx, bucket))
        lines.append(f"| *資本活動淨額* | *{_fmt(cap_net)}* | |")
        lines.append("")

    # --- Balance Sheet ---
    if bs and bs.total_assets > 0:
        lines.append("## 資產負債表\n")
        lines.append(f"| 項目 | 金額 ({base}) | |")
        lines.append("|------|----------:|:--:|")

        rb = bs.risk_buckets
        group_conf = {
            "liquid_cash":  ("流動資產 (Cash)",              C_HARD),
            "equities":     ("股票/ETF (Equities)",          C_EST),
            "bonds":        ("債券/結構型商品 (Bonds)",        C_EST),
            "real_estate":  ("不動產 (Real Estate)",          C_ASSU),
            "insurance":    ("保險價值 (Insurance)",           C_ASSU),
            "other":        ("其他 (Other)",                  C_ASSU),
        }
        details = bs.details
        for group, (label, conf) in group_conf.items():
            val = rb.get(group, 0)
            if val != 0:
                lines.append(f"| {label} | {_fmt(val)} | {conf} |")
                # Show top items in this group
                group_items = [d for d in details if d["group"] == group]
                group_items.sort(key=lambda d: abs(d["amount_twd"]), reverse=True)
                for d in group_items[:8]:
                    name = d["name"][:30]
                    cur_note = f" ({d['currency']})" if d["currency"] != "TWD" else ""
                    lines.append(f"|   ↳ {name}{cur_note} | {_fmt(d['amount_twd'])} | |")
                if len(group_items) > 8:
                    rest = sum(d["amount_twd"] for d in group_items[8:])
                    lines.append(f"|   ↳ ...其他 {len(group_items)-8} 項 | {_fmt(rest)} | |")

        lines.append(f"| **資產合計** | **{_fmt(bs.total_assets)}** | |")

        if bs.total_liabilities > 0:
            liab_items = [d for d in details if d["group"] == "liabilities"]
            lines.append(f"| 負債 | -{_fmt(bs.total_liabilities)} | {C_HARD} |")
            for d in liab_items:
                name = d["name"][:30]
                lines.append(f"|   ↳ {name} | -{_fmt(abs(d['amount_twd']))} | |")

        lines.append(f"| **淨資產** | **{_fmt(bs.net_worth)}** | |")
        lines.append("")

        # Key ratios
        liability_ratio = bs.total_liabilities / bs.total_assets if bs.total_assets else 0
        monthly_exp = cfg["assumptions"].get("monthly_expense", 100000)
        emergency_months = bs.total_cash / monthly_exp if monthly_exp else 0

        lines.append("### 關鍵指標\n")
        lines.append(f"| 指標 | 數值 | |")
        lines.append("|------|------:|:--:|")
        # Liquid equity ratio (excludes real estate from denominator)
        financial_assets = (bs.total_assets
                           - bs.risk_buckets.get("real_estate", 0))
        liquid_eq_ratio = (bs.risk_buckets.get("equities", 0)
                          / financial_assets if financial_assets > 0 else 0)

        lines.append(f"| 負債比 | {_pct(liability_ratio)} | {C_HARD} |")
        lines.append(f"| 金融資產股票比 | {_pct(liquid_eq_ratio)} | {C_HARD} |")
        lines.append(f"| 緊急預備金 | {emergency_months:.1f} 個月 | {C_HARD} |")
        lines.append(f"| 儲蓄率 | {sr_str} | {C_HARD} |")

        if liability_ratio > 0.6:
            lines.append(f"\n> ⚠ 警告：負債比超過 60%")
        lines.append("")

    # --- Cash Flow ---
    lines.append("## 現金流量\n")
    lines.append(f"| | 金額 ({base}) | |")
    lines.append("|--|----------:|:--:|")
    lines.append(f"| 流入 | {_fmt(cash_flow.inflow)} | {C_HARD} |")
    lines.append(f"| 流出 | {_fmt(cash_flow.outflow)} | {C_HARD} |")
    lines.append(f"| **淨流量** | **{_fmt(cash_flow.net_flow)}** | |")
    lines.append("")

    # --- Market Anchors ---
    if market:
        lines.append("## 市場定錨\n")
        lines.append(f"| 指標 | 數值 | |")
        lines.append(f"|------|------:|:--:|")
        labels = {
            "US_10Y_Yield": "美國 10Y 殖利率",
            "BTC_USD": "BTC/USD",
            "Gold": "黃金期貨",
            "USD_TWD": "USD/TWD",
            "TAIEX": "加權指數",
        }
        for key, label in labels.items():
            val = market.get(key)
            if val is not None:
                if "殖利率" in label:
                    lines.append(f"| {label} | {val:.2f}% | {C_EST} |")
                else:
                    lines.append(f"| {label} | {_fmt(val)} | {C_EST} |")
        lines.append("")

    # --- Glide Path ---
    if glide:
        status_icon = {"on_track": "🟢", "minor_drift": "🟡", "major_drift": "🔴"}.get(glide.status, "⚪")
        _status_zh = {"on_track": "正常", "minor_drift": "輕微偏移", "major_drift": "重大偏移"}
        lines.append("## 退休軌道\n")
        lines.append(f"| 指標 | 數值 |")
        lines.append(f"|------|------:|")
        lines.append(f"| 年齡 | {glide.age} |")
        lines.append(f"| 目標股票比 | {_pct(glide.target)} |")
        lines.append(f"| 實際股票比 | {_pct(glide.actual)} |")
        lines.append(f"| 偏移 | {glide.drift:+.1%} |")
        lines.append(f"| 狀態 | {status_icon} **{_status_zh.get(glide.status, glide.status)}** |")
        lines.append(f"\n> {glide.message}")
        lines.append("")

    # --- Warnings ---
    if warnings:
        lines.append("## 注意事項\n")
        for w in warnings:
            lines.append(f"> **WARNING:** {w}\n")

    # --- Footer ---
    lines.append("---\n")
    lines.append(f"*由 [personal-cfo](https://github.com/notoriouslab/personal-cfo) 產生。"
                 f"數據信心：{C_HARD} 對帳單 {C_EST} 市場估值 {C_ASSU} 假設值*\n")

    return "\n".join(lines)


def render_track_report(snapshots, glide, cfg):
    """Render Track mode report from snapshot history.

    Args:
        snapshots: list of snapshot dicts (sorted by period)
        glide: GlideDiagnosis from diagnose_drift
        cfg: config dict
    """
    lines = ["# Track Audit — Retirement Glide Path\n"]

    # Current diagnosis
    if glide:
        status_icon = {"on_track": "🟢", "minor_drift": "🟡", "major_drift": "🔴"}.get(glide.status, "⚪")
        lines.append("## Current Diagnosis\n")
        lines.append(f"- Age: {glide.age}")
        lines.append(f"- Target Equity: {_pct(glide.target)}")
        lines.append(f"- Actual Equity: {_pct(glide.actual)}")
        lines.append(f"- Drift: {glide.drift:+.1%} → {status_icon} **{glide.status.upper()}**")
        lines.append(f"- {glide.message}")
        lines.append("")

    # Trend table
    if len(snapshots) >= 2:
        lines.append("## Trend (趨勢)\n")
        lines.append("| Period | Net Worth | Equity Ratio | Status |")
        lines.append("|--------|----------:|:------------:|--------|")
        for s in snapshots[-6:]:  # last 6 periods
            nw = _fmt(s.get("net_worth", 0))
            er = _pct(s.get("equity_ratio", 0))
            gp = s.get("glide_path")
            if isinstance(gp, GlideDiagnosis):
                st = gp.status
            elif isinstance(gp, dict):
                st = gp.get("status", "—")
            else:
                st = "—"
            lines.append(f"| {s['period']} | {nw} | {er} | {st} |")
        lines.append("")

    # Glide path table
    from .glide_path import glide_path_table
    table = glide_path_table(cfg)
    if table:
        lines.append("## Glide Path Table (滑行路徑)\n")
        lines.append("| Age | Target Equity |")
        lines.append("|----:|--------------:|")
        current_age = glide.age if glide else None
        for age, target in table:
            marker = " ← now" if age == current_age else ""
            lines.append(f"| {age} | {_pct(target)}{marker} |")
        lines.append("")

    return "\n".join(lines)


def render_projection_report(snapshot, rows, summary, cfg):
    """Render retirement projection as Markdown report."""
    lp = cfg["life_plan"]
    assume = cfg["assumptions"]
    proj = cfg.get("projection", {})
    er = proj.get("expected_returns", {})
    period = snapshot.get("period", "unknown")

    lines = []
    lines.append(f"# 退休投影報告 — {period}\n")
    lines.append("> ⚠️ **免責聲明**：本報告基於假設推估，非預測亦非投資建議。")
    lines.append("> 實際結果受市場波動、政策變化、健康狀況等影響，可能大幅偏離推估。")
    lines.append("> 請定期重新評估，並諮詢專業顧問。\n")
    lines.append("---\n")

    # --- Assumptions ---
    lines.append("## 假設參數\n")
    lines.append("| 參數 | 數值 | 來源 |")
    lines.append("|------|-----:|------|")
    lines.append(f"| 出生年 | {lp['birth_year']} | ⚪ config |")
    lines.append(f"| 退休年齡 | {lp['retirement_age']} | ⚪ config |")
    lines.append(f"| 預期壽命 | {lp.get('life_expectancy', 84)} | ⚪ config |")
    lines.append(f"| 每月生活費 | {_fmt(assume['monthly_expense'])} | ⚪ config |")
    lines.append(f"| 通膨率 | {_pct(assume.get('inflation_rate', 0.025))}/年 | ⚪ config |")
    savings = assume.get("annual_savings", 0)
    lines.append(f"| 年度儲蓄 | {_fmt(savings)} | ⚪ config |")
    pension = lp.get("expected_pension_monthly", 0)
    if pension > 0:
        lines.append(f"| 退休後月領年金 | {_fmt(pension)} | ⚪ config (勞保+勞退) |")
    for bucket in ("equities", "bonds", "liquid_cash", "insurance"):
        label = {"equities": "股票預期報酬", "bonds": "債券預期報酬",
                 "liquid_cash": "現金利率",
                 "insurance": "保險增值"}.get(bucket, bucket)
        rate = er.get(bucket, 0)
        lines.append(f"| {label} | {_pct(rate)}/年 | ⚪ config |")
    lines.append("")

    # --- Readiness ---
    lines.append("## 退休準備度\n")
    lines.append("| 指標 | 數值 |")
    lines.append("|------|-----:|")
    lines.append(f"| 現在年齡 | {summary['current_age']} |")
    lines.append(f"| 距退休 | {summary['years_to_retirement']} 年 |")
    lines.append(f"| 退休後年數 | {summary['years_in_retirement']} 年 |")
    lines.append(f"| 目前淨資產 | {_fmt(round(snapshot.get('net_worth', 0)))} |")

    from .projection import split_liquid_illiquid
    liquid, illiquid = split_liquid_illiquid(snapshot.get("risk_buckets", {}))
    lines.append(f"| 目前流動資產 | {_fmt(round(liquid))} |")
    lines.append(f"| 預估退休時淨資產 | {_fmt(round(summary['retire_start_net_worth']))} |")
    lines.append(f"| 預估退休時流動資產 | {_fmt(round(summary['retire_start_liquid']))} |")
    lines.append(f"| 退休首年花費 | {_fmt(round(summary['retire_expense_start']))}/年 |")
    lines.append(f"| 退休末年花費（含通膨） | {_fmt(round(summary['retire_expense_end']))}/年 |")
    lines.append(f"| 預估壽終時淨資產 | {_fmt(round(summary['final_net_worth']))} |")

    # Safe withdrawal rate benchmarks
    # 4% is US historical; 3.5% is more conservative for non-US markets
    retire_exp = summary.get("retire_expense_start", 0)
    retire_liq = summary.get("retire_start_liquid", 0)
    if retire_exp > 0:
        for rate, label in [(0.04, "4%"), (0.035, "3.5%")]:
            req = retire_exp / rate
            ratio = retire_liq / req if req > 0 else 0
            status = "✅" if ratio >= 1.0 else "⚠️"
            pct_label = _pct(ratio) if ratio <= 5 else f"{ratio:.1f}x"
            lines.append(f"| {label} Rule 所需退休金 | {_fmt(round(req))} ({status} {pct_label}) |")

    dep = summary["depleted_age"]
    if dep:
        lines.append(f"| 資金枯竭年齡 | ⚠️ {dep} 歲 |")
    else:
        lines.append("| 資金枯竭年齡 | ✅ 不會 |")

    sus = summary["sustainability"]
    sus_label = {"sustainable": "🟢 可持續", "at_risk": "🟡 有風險",
                 "depleted": "🔴 資金不足"}[sus]
    lines.append(f"| 退休可行性 | {sus_label} |")
    lines.append("")

    # --- Year-by-year table ---
    lines.append("## 年度投影\n")
    lines.append("| 年齡 | 年 | 階段 | 流動資產 | 年度花費 | 流動收益 | 淨資產 |")
    lines.append("|-----:|----:|:----:|---------:|---------:|---------:|-------:|")

    retirement_age = lp["retirement_age"]
    for r in rows:
        phase_label = "累積" if r.phase == "accumulation" else "退休"
        expense_col = "—" if r.phase == "accumulation" else _fmt(round(r.annual_expense))
        marker = ""
        if r.age == retirement_age:
            marker = " ← 退休"
        elif r.depleted:
            marker = " ⚠️"
        lines.append(
            f"| {r.age} | {r.year} | {phase_label} | "
            f"{_fmt(round(r.liquid_assets))} | {expense_col} | "
            f"{_fmt(round(r.liquid_gain))} | "
            f"{_fmt(round(r.net_worth))}{marker} |"
        )
    lines.append("")

    # --- Warnings ---
    lines.append("")
    lines.append("> 「流動收益」僅含可提領資產的投資報酬。"
                 "不動產增值另計入淨資產但不可提領。\n")

    lines.append("## 注意事項\n")
    if illiquid > 0:
        lines.append(f"> ⚠️ 不動產 {_fmt(round(illiquid))} 以**原值**計入淨資產，"
                     f"不做增值假設，且**不可提領**。退休提領僅來自流動資產。\n")
    lines.append("> ⚠️ 本推估未考慮：稅負、重大醫療支出（醫療通膨通常為一般通膨 2-3 倍）、"
                 "市場崩盤序列風險（sequence-of-returns risk）。\n")
    lines.append("> 📖 提領率參考：Bengen (1994) 4%、Trinity Study (1998)。"
                 "台灣本土市場建議 3-3.5%（波動較大、匯率風險）。"
                 "壽命：內政部 2024 簡易生命表。"
                 "報酬率：FP Canada 2025 PAG。\n")
    lines.append("---\n")
    lines.append("*由 personal-cfo 產生。所有數據皆為 ⚪ 假設推估值*")

    return "\n".join(lines)

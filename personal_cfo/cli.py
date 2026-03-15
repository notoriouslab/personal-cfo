"""CLI entry point for personal-cfo."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from . import __version__
from .config import load_config
from .fx import make_fx
from .models import Transaction
from .parser import parse_csv, parse_assets_csv, parse_markdown_dir, parse_single_md
from .accounting import compute_income_statement, compute_balance_sheet, compute_cash_flow
from .market import fetch_market_anchors
from .glide_path import diagnose_drift
from .report import render_cfo_report, render_track_report

import re
_SAFE_PERIOD = re.compile(r"^\d{4}-\d{2}$")


def _validate_period(period):
    """Validate period string to prevent path traversal."""
    if period and not _SAFE_PERIOD.match(period):
        print(f"Error: Invalid period format '{period}'. Expected YYYY-MM (e.g. 2026-01).", file=sys.stderr)
        sys.exit(1)
    return period


def _atomic_write(path, content):
    """Write content to file atomically."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
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


def _save_snapshot(bs, period, output_dir):
    """Save asset snapshot JSON for track mode."""
    eq = bs.risk_buckets.get("equities", 0)
    non_investable = bs.risk_buckets.get("real_estate", 0) + bs.risk_buckets.get("insurance", 0)
    total_investable = bs.total_assets - non_investable
    equity_ratio = eq / total_investable if total_investable > 0 else 0

    snapshot = {
        "period": period,
        "net_worth": round(bs.net_worth, 2),
        "total_assets": round(bs.total_assets, 2),
        "total_liabilities": round(bs.total_liabilities, 2),
        "total_cash": round(bs.total_cash, 2),
        "equity_ratio": round(equity_ratio, 4),
        "risk_buckets": {k: round(v, 2) for k, v in bs.risk_buckets.items()},
    }

    snap_dir = Path(output_dir) / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    snap_path = snap_dir / f"{period}_asset_snapshot.json"
    _atomic_write(str(snap_path), json.dumps(snapshot, indent=2, ensure_ascii=False))
    print(f"  Snapshot saved: {snap_path}")
    return snapshot


def cmd_cfo(args):
    """Run CFO mode — monthly financial audit."""
    _validate_period(args.period)  # guard early before any file I/O
    cfg = load_config(args.config)
    to_twd = make_fx(cfg.get("fx_rates", {}))
    category_rules = cfg.get("category_rules", {})

    all_tx = []
    all_assets = []

    # Parse transactions
    for tx_path in args.transactions:
        p = Path(tx_path)
        if p.is_dir():
            # Markdown directory mode
            prefix = args.period.replace("-", "") if args.period else None
            tx, assets, vendors = parse_markdown_dir(p, prefix=prefix, category_rules=category_rules)
            all_tx.extend(tx)
            all_assets.extend(assets)
            print(f"  Parsed directory: {p} ({len(tx)} transactions, {len(assets)} assets)")
        elif p.suffix == ".csv":
            tx = parse_csv(str(p), category_rules=category_rules)
            all_tx.extend(tx)
            print(f"  Parsed CSV: {p} ({len(tx)} transactions)")
        elif p.suffix == ".md":
            # Single markdown file
            tx, assets = parse_single_md(p, category_rules=category_rules)
            all_tx.extend(tx)
            all_assets.extend(assets)
            print(f"  Parsed MD: {p.name} ({len(tx)} tx, {len(assets)} assets)")

    # Parse separate assets file if provided
    if args.assets:
        csv_assets = parse_assets_csv(args.assets)
        all_assets.extend(csv_assets)
        print(f"  Parsed assets: {args.assets} ({len(csv_assets)} items)")

    if not all_tx and not all_assets:
        print("Error: No data found. Check your input paths.")
        sys.exit(1)

    # Warn about potential CC double-counting
    cc_double_warn = None
    cc_accounts = {t.account for t in all_tx
                   if isinstance(t, Transaction) and ("信用卡" in t.account or "credit" in t.account.lower())}
    if cc_accounts:
        card_payment_tx = [t for t in all_tx
                          if isinstance(t, Transaction) and t.account not in cc_accounts and "卡費" in t.description]
        if card_payment_tx:
            cc_count = sum(len([t for t in all_tx if isinstance(t, Transaction) and t.account == a]) for a in cc_accounts)
            cc_double_warn = (f"偵測到 {len(card_payment_tx)} 筆銀行端卡費扣款 + "
                              f"{cc_count} 筆信用卡消費明細。"
                              f"若兩邊都匯入，請在 category_rules 中將卡費標為 internal_transfer，"
                              f"否則支出會重複計算。")
            print(f"  WARNING: {cc_double_warn}", file=sys.stderr)

    # Inject annual expenses as prorated monthly transactions
    annual_expenses = cfg.get("annual_expenses", [])
    for ae in annual_expenses:
        raw = ae["amount"]
        # Positive amount = expense (negate it); negative = income (keep sign)
        monthly_amt = (-abs(raw) if raw > 0 else abs(raw)) / 12
        all_tx.append(Transaction(
            date="",
            description=ae.get("name", "年度費用"),
            amount=monthly_amt,
            currency=ae.get("currency", "TWD"),
            category=ae.get("category", ""),
            account="config (年度分攤)",
        ))
    if annual_expenses:
        print(f"  Injected {len(annual_expenses)} annual expenses (prorated monthly)")

    print(f"\n  Total: {len(all_tx)} transactions, {len(all_assets)} assets\n")

    # Compute
    is_buckets, classified_tx = compute_income_statement(all_tx, to_twd)
    manual_assets = cfg.get("manual_assets", [])
    bs = compute_balance_sheet(all_assets, manual_assets, to_twd) if all_assets else None

    cash_flow = compute_cash_flow(is_buckets)

    # Output dir (resolve early for cache_dir)
    output_dir = args.output or "output"
    period = args.period or "unknown"

    cache_dir = str(Path(output_dir) / ".cache")
    market = fetch_market_anchors(offline=args.offline, cache_dir=cache_dir)

    # Glide path diagnosis
    glide = None
    if bs and bs.total_assets > 0:
        eq = bs.risk_buckets.get("equities", 0)
        non_investable = bs.risk_buckets.get("real_estate", 0) + bs.risk_buckets.get("insurance", 0)
        total_investable = bs.total_assets - non_investable
        equity_ratio = eq / total_investable if total_investable > 0 else 0
        if not (0 <= equity_ratio <= 1.0):
            print(f"  WARNING: equity_ratio={equity_ratio:.2%} is outside [0, 100%]. "
                  f"Check asset classification.", file=sys.stderr)
            equity_ratio = max(0, min(1.0, equity_ratio))
        glide = diagnose_drift(equity_ratio, cfg)

    # Render report
    warnings = []
    if cc_double_warn:
        warnings.append(cc_double_warn)
    report = render_cfo_report(period, is_buckets, bs, cash_flow, market, glide, cfg,
                               classified_tx=classified_tx, warnings=warnings)

    # Output
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    report_path = Path(output_dir) / f"financial_report_{period}.md"
    _atomic_write(str(report_path), report)
    print(f"  Report saved: {report_path}")

    # Save snapshot for track mode
    if bs:
        _save_snapshot(bs, period, output_dir)

    if not args.quiet:
        print(f"\n{'='*60}")
        print(report)


def cmd_track(args):
    """Run Track mode — retirement glide path audit."""
    cfg = load_config(args.config)

    snap_dir = Path(args.snapshots)
    if not snap_dir.exists():
        print(f"Error: Snapshots directory not found: {snap_dir}")
        sys.exit(1)

    # Load all snapshots
    snapshots = []
    for f in sorted(snap_dir.glob("*_asset_snapshot.json")):
        try:
            data = json.loads(f.read_text())
            # Only monthly snapshots (period like "2026-01")
            if len(data.get("period", "")) == 7:
                snapshots.append(data)
        except Exception:
            pass

    if not snapshots:
        print("Error: No valid snapshots found.")
        sys.exit(1)

    print(f"  Loaded {len(snapshots)} snapshots")

    # Use latest snapshot for diagnosis
    latest = snapshots[-1]
    equity_ratio = latest.get("equity_ratio", 0)
    glide = diagnose_drift(equity_ratio, cfg)

    # Enrich snapshots with glide path info
    for s in snapshots:
        s["glide_path"] = diagnose_drift(s.get("equity_ratio", 0), cfg)

    # Render
    report = render_track_report(snapshots, glide, cfg)

    output_dir = args.output or "output"
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    report_path = Path(output_dir) / f"track_audit_{latest['period']}.md"
    _atomic_write(str(report_path), report)
    print(f"  Report saved: {report_path}")

    if not args.quiet:
        print(f"\n{'='*60}")
        print(report)


def main():
    parser = argparse.ArgumentParser(
        prog="personal-cfo",
        description="CLI-first retirement glide path financial analyzer",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    # CFO mode
    cfo = sub.add_parser("cfo", help="Monthly financial audit")
    cfo.add_argument("--transactions", "-t", nargs="+", required=True,
                     help="Transaction CSV files, Markdown files, or directory of .md files")
    cfo.add_argument("--assets", "-a", help="Assets CSV file (optional)")
    cfo.add_argument("--period", "-p", help="Period label (e.g. 2026-01)")
    cfo.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    cfo.add_argument("--output", "-o", help="Output directory")
    cfo.add_argument("--offline", action="store_true", help="Skip network calls")
    cfo.add_argument("--quiet", "-q", action="store_true", help="Only save files, no stdout")

    # Track mode
    track = sub.add_parser("track", help="Retirement glide path audit")
    track.add_argument("--snapshots", "-s", required=True, help="Directory of snapshot JSON files")
    track.add_argument("--config", "-c", default="config.yaml", help="Config file path")
    track.add_argument("--output", "-o", help="Output directory")
    track.add_argument("--quiet", "-q", action="store_true", help="Only save files, no stdout")

    args = parser.parse_args()

    if args.command == "cfo":
        cmd_cfo(args)
    elif args.command == "track":
        cmd_track(args)
    else:
        parser.print_help()
        sys.exit(1)

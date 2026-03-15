"""Markdown + JSON parsers — doc-cleaner pipeline and plain markdown."""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from ..models import Transaction, Asset
from ._io import _try_read
from ._normalize import _clean_amount, _classify, _detect_currency_from_desc, _normalize_date
from ._pipe_table import _parse_tables_from_markdown, _parse_assets_from_tables


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
    _asset_currencies = {a.get("currency", "").upper()
                         for a in assets_raw if a.get("currency")}
    _asset_currencies.discard("")
    inferred_currency = None
    if len(_asset_currencies) == 1:
        only_cur = _asset_currencies.pop()
        if only_cur != "TWD":
            inferred_currency = only_cur
    elif len(_asset_currencies) > 1:
        print(f"  NOTE: {p.name}: assets have mixed currencies "
              f"({', '.join(sorted(_asset_currencies))}). "
              f"Transactions without explicit currency will default to TWD.",
              file=sys.stderr)

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

        transactions.append(Transaction(
            date=t.get("date", ""),
            description=t.get("description", ""),
            amount=amt,
            currency=currency,
            category=cat,
            account=vendor,
        ))

    assets = []
    for a in assets_raw:
        assets.append(Asset(
            name=a.get("name", "Unknown"),
            category=a.get("category", "Unknown"),
            amount=_clean_amount(a.get("amount", 0)),
            currency=a.get("currency", "TWD"),
            vendor=vendor,
        ))

    # --- Supplement / Fallback: cross-check with refined_markdown ---
    md_text = data.get("refined_markdown", "")
    if md_text:
        pipe_tx = _parse_tables_from_markdown(
            md_text, is_cc=is_cc, vendor=vendor,
            category_rules=category_rules,
        )
        if pipe_tx:
            if not transactions and not assets:
                transactions = pipe_tx
                print(f"  NOTE: {p.name}: extracted {len(pipe_tx)} "
                      f"transactions from pipe tables (fallback mode)",
                      file=sys.stderr)
            elif transactions:
                # Cross-reference with multi-map for collision safety
                json_by_sig = defaultdict(list)
                for idx, t in enumerate(transactions):
                    sig = (_normalize_date(t.date),
                           round(abs(t.amount)))
                    json_by_sig[sig].append(idx)

                sig_match_count = defaultdict(int)

                supplemented = 0
                enriched = 0
                for pt in pipe_tx:
                    sig = (_normalize_date(pt.date),
                           round(abs(pt.amount)))
                    indices = json_by_sig.get(sig, [])
                    match_offset = sig_match_count[sig]
                    if match_offset < len(indices):
                        idx = indices[match_offset]
                        sig_match_count[sig] += 1
                        if (pt.description != transactions[idx].description
                                and category_rules):
                            new_cat = _classify(
                                pt.description, category_rules)
                            old_cat = transactions[idx].category
                            if new_cat and new_cat != old_cat and (
                                    old_cat in ("", "internal_transfer")):
                                transactions[idx].description = \
                                    pt.description
                                transactions[idx].category = new_cat
                                enriched += 1
                    else:
                        transactions.append(pt)
                        json_by_sig[sig].append(len(transactions) - 1)
                        sig_match_count[sig] += 1
                        supplemented += 1

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
    """Check if a file matches the target period."""
    if prefix and path.name.startswith(prefix):
        return True
    if not target_year or not target_month:
        return not prefix

    try:
        content = _try_read(path)
    except ValueError:
        return False

    # Check STRUCTURED_DATA JSON
    try:
        data = _extract_json_from_md(content)
        if data and isinstance(data, dict):
            month_val = data.get("month", "")
            try:
                month_int = int(month_val)
                if not (1 <= month_int <= 12):
                    month_val = ""
            except (ValueError, TypeError):
                month_val = ""
            if (str(data.get("year", "")) == target_year
                    and str(month_val).zfill(2) == target_month):
                return True
    except (json.JSONDecodeError, Exception):
        pass

    # Check YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            fm = content[3:end]
            y_match = re.search(r'^year:\s*["\']?(\d{4})', fm, re.MULTILINE)
            m_match = re.search(r'^month:\s*["\']?(\d{1,2})', fm, re.MULTILINE)
            if y_match and m_match:
                month_int = int(m_match.group(1))
                if not (1 <= month_int <= 12):
                    return False
                if (y_match.group(1) == target_year
                        and m_match.group(1).zfill(2) == target_month):
                    return True

    return False


def parse_markdown_dir(dir_path, prefix=None, category_rules=None):
    """Scan directory for Markdown files with STRUCTURED_DATA.

    Returns (all_transactions, all_assets, vendors).
    """
    dir_path = Path(dir_path)
    all_tx = []
    all_assets = []
    vendors = set()

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
        if tx:
            vendors.add(tx[0].account)
        elif assets:
            vendors.add(assets[0].vendor or md_file.stem)

    return all_tx, all_assets, vendors

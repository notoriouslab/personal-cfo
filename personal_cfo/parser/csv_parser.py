"""CSV format parsers — transactions and assets."""

import csv
import io

from ..models import Transaction, Asset
from ._io import _try_read
from ._normalize import _clean_amount, _classify


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

        transactions.append(Transaction(
            date=row["date"].strip(),
            description=row.get("description", "").strip(),
            amount=amt,
            currency=row.get("currency", "TWD").strip().upper() or "TWD",
            category=cat,
            account=row.get("account", "").strip(),
        ))

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
        assets.append(Asset(
            name=row.get("account", row.get("name", "Unknown")).strip(),
            category=row.get("category", "Unknown").strip(),
            amount=amt,
            currency=row.get("currency", "TWD").strip().upper() or "TWD",
        ))
    return assets

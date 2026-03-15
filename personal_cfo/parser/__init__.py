"""Parse financial data from CSV or Markdown+JSON (doc-cleaner output).

Supports three input modes:
1. CSV — universal, user-provided
2. Markdown with transactions[]/assets[] JSON — pre-structured
3. Markdown with refined_markdown only — fallback, extracts from pipe tables
"""

# Public API — re-exported from submodules
from .csv_parser import parse_csv, parse_assets_csv
from .md_parser import parse_single_md, parse_markdown_dir

# Internal helpers exposed for tests
from ._normalize import (
    _clean_amount, _classify, _normalize_currency,
    _detect_currency_from_desc, _normalize_date,
)
from ._pipe_table import (
    _parse_tables_from_markdown, _parse_assets_from_tables,
    _find_col, _infer_asset_category,
)
from ._io import _try_read

__all__ = [
    "parse_csv", "parse_assets_csv", "parse_single_md", "parse_markdown_dir",
    "_clean_amount", "_classify", "_normalize_currency",
    "_detect_currency_from_desc", "_normalize_date",
    "_parse_tables_from_markdown", "_parse_assets_from_tables",
    "_find_col", "_infer_asset_category", "_try_read",
]

"""Tests for parser — CSV, Markdown pipe tables, JSON+markdown, cross-reference."""

import json
import os
import tempfile
import pytest
from pathlib import Path
from personal_cfo.parser import (
    parse_csv, parse_assets_csv, parse_single_md,
    _parse_tables_from_markdown, _clean_amount, _classify,
    _normalize_currency, _detect_currency_from_desc,
)


# ---------- _clean_amount ----------

class TestCleanAmount:
    def test_int(self):
        assert _clean_amount(150000) == 150000.0

    def test_float(self):
        assert _clean_amount(3.14) == 3.14

    def test_string_with_commas(self):
        assert _clean_amount("150,000") == 150000.0

    def test_string_with_bold_markdown(self):
        assert _clean_amount("**150,000**") == 150000.0

    def test_string_with_dollar_sign(self):
        assert _clean_amount("$1,200") == 1200.0

    def test_dash_returns_zero(self):
        assert _clean_amount("-") == 0.0

    def test_empty_returns_zero(self):
        assert _clean_amount("") == 0.0

    def test_trailing_parenthetical_stripped(self):
        assert _clean_amount("1000(97.38%)") == 1000.0

    def test_rejects_nan(self):
        with pytest.raises(ValueError):
            _clean_amount(float("nan"))

    def test_rejects_absurd_values(self):
        with pytest.raises(ValueError):
            _clean_amount("99999999999999")


# ---------- _classify ----------

class TestClassify:
    def test_matches_keyword(self):
        rules = {"薪資": "salary", "保險": "insurance"}
        assert _classify("薪資入帳", rules) == "salary"

    def test_case_insensitive(self):
        rules = {"salary": "salary"}
        assert _classify("Monthly SALARY", rules) == "salary"

    def test_no_match_returns_none(self):
        rules = {"薪資": "salary"}
        assert _classify("grocery", rules) is None

    def test_order_matters(self):
        """First matching rule wins."""
        from collections import OrderedDict
        rules = OrderedDict([("獎金薪資", "bonus"), ("薪資", "salary")])
        assert _classify("獎金薪資入帳", rules) == "bonus"


# ---------- _normalize_currency ----------

class TestNormalizeCurrency:
    def test_iso_passthrough(self):
        assert _normalize_currency("USD") == "USD"

    def test_chinese_mapping(self):
        assert _normalize_currency("美元") == "USD"
        assert _normalize_currency("日圓") == "JPY"
        assert _normalize_currency("臺幣") == "TWD"

    def test_unknown_defaults_twd(self):
        assert _normalize_currency("unknown") == "TWD"


# ---------- _detect_currency_from_desc ----------

class TestDetectCurrencyFromDesc:
    def test_parenthetical_code(self):
        assert _detect_currency_from_desc("基金配息 (CNY)") == "CNY"

    def test_chinese_prefix(self):
        assert _detect_currency_from_desc("美元活存: 信託 法興") == "USD"

    def test_twd_prefix(self):
        assert _detect_currency_from_desc("台幣活存: 繳放款") == "TWD"

    def test_fold_twd(self):
        """折TWD means already converted."""
        assert _detect_currency_from_desc("美元活存: 折TWD 利息") == "TWD"

    def test_no_hint(self):
        assert _detect_currency_from_desc("Grocery Store") is None


# ---------- parse_csv ----------

class TestParseCSV:
    @pytest.fixture
    def sample_csv(self):
        return Path(__file__).parent.parent / "examples" / "sample_transactions.csv"

    def test_parses_all_rows(self, sample_csv):
        tx = parse_csv(sample_csv)
        assert len(tx) == 10

    def test_applies_category_rules(self, sample_csv):
        rules = {"Salary": "salary", "Grocery": "grocery"}
        tx = parse_csv(sample_csv, category_rules=rules)
        salary_tx = [t for t in tx if t.category == "salary"]
        assert len(salary_tx) >= 1

    def test_preserves_user_category(self, sample_csv):
        """Existing category in CSV should be used when no rule matches."""
        tx = parse_csv(sample_csv)
        housing = [t for t in tx if t.category == "housing"]
        assert len(housing) == 1

    def test_zero_amount_skipped(self, tmp_path):
        csv_file = tmp_path / "zero.csv"
        csv_file.write_text("date,description,amount\n2026-01-01,Nothing,0\n")
        tx = parse_csv(csv_file)
        assert len(tx) == 0


# ---------- parse_assets_csv ----------

class TestParseAssetsCSV:
    def test_parses_sample(self):
        path = Path(__file__).parent.parent / "examples" / "sample_assets.csv"
        assets = parse_assets_csv(path)
        assert len(assets) == 7
        cash = [a for a in assets if a.category == "Cash"]
        assert len(cash) == 3


# ---------- _parse_tables_from_markdown ----------

class TestParseTablesFromMarkdown:
    def test_split_debit_credit(self):
        """Bank statement with separate 支出/存入 columns."""
        md = """\
| 日期 | 摘要 | 支出 | 存入 |
| :--- | :--- | :--- | :--- |
| 2026/01/05 | Salary | | 150,000 |
| 2026/01/10 | Mortgage | 25,000 | |
"""
        tx = _parse_tables_from_markdown(md, vendor="test")
        assert len(tx) == 2
        salary = tx[0]
        assert salary.amount == 150000
        assert salary.date == "2026-01-05"
        mortgage = tx[1]
        assert mortgage.amount == -25000

    def test_single_amount_column(self):
        """Credit card with single 金額 column."""
        md = """\
| 消費日 | 說明 | 臺幣金額 |
| :--- | :--- | :--- |
| 2026/01/05 | Restaurant | 1,200 |
| 2026/01/08 | Online Shop | 3,500 |
"""
        tx = _parse_tables_from_markdown(md, is_cc=True, vendor="cc")
        assert len(tx) == 2
        assert tx[0].amount == -1200  # CC sign flip

    def test_debit_credit_priority_over_amount(self):
        """Bug fix: when both 支出/存入 AND 金額 columns exist,
        prefer debit/credit split (金額 may match wrong column)."""
        md = """\
| 日期 | 摘要 | 支出金額 | 存入金額 |
| :--- | :--- | :--- | :--- |
| 2026/01/05 | Salary | | 150,000 |
| 2026/01/10 | Rent | 30,000 | |
"""
        tx = _parse_tables_from_markdown(md, vendor="test")
        assert len(tx) == 2
        assert tx[0].amount == 150000  # salary is credit
        assert tx[1].amount == -30000  # rent is debit

    def test_remarks_column_merged(self):
        """Bug fix: remarks column content should be merged into description."""
        md = """\
| 日期 | 摘要 | 支出 | 存入 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| 2026/01/05 | 轉帳 | 50,000 | | 轉出123456薪轉 |
"""
        rules = {"轉出123456薪轉": "salary"}
        tx = _parse_tables_from_markdown(md, vendor="test",
                                         category_rules=rules)
        assert len(tx) == 1
        assert tx[0].category == "salary"
        assert "轉出123456薪轉" in tx[0].description

    def test_remarks_not_duplicated(self):
        """Don't append remark if it's already in description."""
        md = """\
| 日期 | 摘要 | 支出 | 存入 | 備註 |
| :--- | :--- | :--- | :--- | :--- |
| 2026/01/05 | 薪資入帳 | | 150,000 | 薪資入帳 |
"""
        tx = _parse_tables_from_markdown(md, vendor="test")
        assert tx[0].description == "薪資入帳"  # not duplicated

    def test_bold_dates_skipped(self):
        """Summary rows with bold dates should be skipped."""
        md = """\
| 日期 | 摘要 | 金額 |
| :--- | :--- | :--- |
| 2026/01/05 | Item | 1,000 |
| **合計** | **Total** | **1,000** |
"""
        tx = _parse_tables_from_markdown(md, vendor="test")
        assert len(tx) == 1

    def test_currency_column_detected(self):
        md = """\
| 日期 | 摘要 | 金額 | 幣別 |
| :--- | :--- | :--- | :--- |
| 2026/01/05 | FX interest | 100 | 美元 |
"""
        tx = _parse_tables_from_markdown(md, vendor="test")
        assert tx[0].currency == "USD"


# ---------- parse_single_md: STRUCTURED_DATA ----------

class TestParseSingleMd:
    def _write_md(self, tmp_path, filename, content):
        p = tmp_path / filename
        p.write_text(content, encoding="utf-8")
        return p

    def test_json_transactions(self, tmp_path):
        content = """\
# Statement

<!-- STRUCTURED_DATA_START
{
  "vendor": "TestBank",
  "transactions": [
    {"date": "2026-01-05", "description": "Salary", "amount": 150000},
    {"date": "2026-01-10", "description": "Grocery", "amount": -3500}
  ],
  "assets": [
    {"name": "Checking", "category": "Cash", "amount": 1500000, "currency": "TWD"}
  ]
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "test_bank.md", content)
        tx, assets = parse_single_md(p)
        assert len(tx) == 2
        assert len(assets) == 1
        assert tx[0].amount == 150000
        assert tx[0].account == "TestBank"

    def test_credit_card_sign_flip(self, tmp_path):
        content = """\
<!-- STRUCTURED_DATA_START
{
  "vendor": "TestCC",
  "transactions": [
    {"date": "2026-01-05", "description": "Shop", "amount": 1200}
  ],
  "assets": []
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "test_信用卡.md", content)
        tx, _ = parse_single_md(p)
        assert tx[0].amount == -1200  # sign flipped for CC

    def test_plain_markdown_no_json(self, tmp_path):
        content = """\
| 日期 | 摘要 | 支出 | 存入 |
| :--- | :--- | :--- | :--- |
| 2026/01/05 | Salary | | 150,000 |
| 2026/01/10 | Rent | 30,000 | |
"""
        p = self._write_md(tmp_path, "plain_statement.md", content)
        tx, assets = parse_single_md(p)
        assert len(tx) == 2
        assert assets == []

    def test_cross_reference_supplements_missing(self, tmp_path):
        """Bug fix: when JSON is incomplete, pipe tables supplement missing tx."""
        # JSON has only 1 transaction, pipe table has 2
        content = """\
<!-- STRUCTURED_DATA_START
{
  "vendor": "TestBank",
  "transactions": [
    {"date": "2026-01-05", "description": "Salary", "amount": 150000}
  ],
  "assets": [],
  "refined_markdown": "| 日期 | 摘要 | 支出 | 存入 |\\n| :--- | :--- | :--- | :--- |\\n| 2026/01/05 | Salary | | 150,000 |\\n| 2026/01/10 | Rent | 30,000 | |"
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "test_bank.md", content)
        tx, _ = parse_single_md(p)
        # Should have 2: the original + supplemented from pipe table
        assert len(tx) == 2
        descs = {t.description for t in tx}
        assert "Salary" in descs
        assert "Rent" in descs

    def test_cross_reference_enriches_description(self, tmp_path):
        """Bug fix: pipe table may have richer description for classification."""
        rules = {"轉出123456": "salary"}
        content = """\
<!-- STRUCTURED_DATA_START
{
  "vendor": "TestBank",
  "transactions": [
    {"date": "2026-01-05", "description": "轉帳", "amount": 150000}
  ],
  "assets": [],
  "refined_markdown": "| 日期 | 摘要 | 支出 | 存入 | 備註 |\\n| :--- | :--- | :--- | :--- | :--- |\\n| 2026/01/05 | 轉帳 轉出123456 | | 150,000 | |"
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "test_bank.md", content)
        tx, _ = parse_single_md(p, category_rules=rules)
        # The enriched description should allow the rule to match
        assert tx[0].category == "salary"

    def test_fallback_when_json_empty(self, tmp_path):
        """When JSON has refined_markdown but no transactions, fall back to pipe tables."""
        content = """\
<!-- STRUCTURED_DATA_START
{
  "vendor": "TestBank",
  "transactions": [],
  "assets": [],
  "refined_markdown": "| 日期 | 摘要 | 金額 |\\n| :--- | :--- | :--- |\\n| 2026/01/05 | Item | 1,000 |"
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "test_bank.md", content)
        tx, _ = parse_single_md(p)
        assert len(tx) == 1

    def test_inferred_currency_from_assets(self, tmp_path):
        """When all assets share a non-TWD currency, infer for transactions."""
        content = """\
<!-- STRUCTURED_DATA_START
{
  "vendor": "Broker",
  "transactions": [
    {"date": "2026-01-05", "description": "Dividend", "amount": 100}
  ],
  "assets": [
    {"name": "VT", "category": "Equity", "amount": 30000, "currency": "USD"},
    {"name": "BND", "category": "Bond", "amount": 10000, "currency": "USD"}
  ]
}
STRUCTURED_DATA_END -->
"""
        p = self._write_md(tmp_path, "broker.md", content)
        tx, _ = parse_single_md(p)
        assert tx[0].currency == "USD"


# ---------- parse_csv edge cases ----------

class TestParseCSVEdgeCases:
    def test_missing_optional_columns(self, tmp_path):
        csv_file = tmp_path / "minimal.csv"
        csv_file.write_text(
            "date,description,amount\n"
            "2026-01-01,Salary,150000\n"
        )
        tx = parse_csv(csv_file)
        assert len(tx) == 1
        assert tx[0].currency == "TWD"  # default
        assert tx[0].category == ""  # no rules

    def test_big5_encoding(self, tmp_path):
        csv_file = tmp_path / "big5.csv"
        csv_file.write_bytes(
            "date,description,amount\n2026-01-01,薪資,150000\n"
            .encode("big5")
        )
        tx = parse_csv(csv_file)
        assert len(tx) == 1
        assert tx[0].description == "薪資"

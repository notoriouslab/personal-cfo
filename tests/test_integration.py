"""Integration test — full pipeline with sample data."""

import pytest
from pathlib import Path
from personal_cfo.config import load_config
from personal_cfo.parser import (
    parse_csv, parse_assets_csv, parse_single_md, parse_markdown_dir,
)
from personal_cfo.fx import make_fx
from personal_cfo.accounting import (
    compute_income_statement, compute_balance_sheet, compute_cash_flow,
    IS_SALARY, IS_INVEST_INCOME, IS_PRINCIPAL, IS_INTEREST,
)
from personal_cfo.glide_path import target_equity_ratio, diagnose_drift


EXAMPLES = Path(__file__).parent.parent / "examples"


class TestFullPipelineCSV:
    """End-to-end: CSV → accounting → glide path."""

    @pytest.fixture
    def cfg(self):
        config_path = EXAMPLES.parent / "config.example.yaml"
        return load_config(str(config_path))

    @pytest.fixture
    def transactions(self, cfg):
        return parse_csv(EXAMPLES / "sample_transactions.csv",
                         category_rules=cfg["category_rules"])

    @pytest.fixture
    def assets(self):
        return parse_assets_csv(EXAMPLES / "sample_assets.csv")

    def test_transactions_parsed(self, transactions):
        assert len(transactions) > 0

    def test_income_statement(self, transactions, cfg):
        to_twd = make_fx(cfg["fx_rates"])
        buckets, classified = compute_income_statement(transactions, to_twd)
        assert buckets[IS_SALARY] > 0
        assert len(classified) > 0

    def test_balance_sheet(self, assets, cfg):
        to_twd = make_fx(cfg["fx_rates"])
        bs = compute_balance_sheet(assets, cfg["manual_assets"], to_twd)
        assert bs["total_assets"] > 0
        assert bs["net_worth"] != 0

    def test_cash_flow(self, transactions, cfg):
        to_twd = make_fx(cfg["fx_rates"])
        buckets, _ = compute_income_statement(transactions, to_twd)
        cf = compute_cash_flow(buckets)
        assert cf["inflow"] > 0
        assert cf["outflow"] < 0

    def test_glide_path(self, assets, cfg):
        to_twd = make_fx(cfg["fx_rates"])
        bs = compute_balance_sheet(assets, cfg["manual_assets"], to_twd)
        total = bs["total_assets"]
        equities = bs["risk_buckets"]["equities"]
        actual_ratio = equities / total if total > 0 else 0
        result = diagnose_drift(actual_ratio, cfg)
        assert result["status"] in ("on_track", "minor_drift", "major_drift")


class TestFullPipelineMarkdown:
    """End-to-end: plain Markdown → accounting."""

    def test_sample_statement(self):
        path = EXAMPLES / "sample_statement.md"
        if not path.exists():
            pytest.skip("sample_statement.md not found")
        tx, assets = parse_single_md(path)
        assert len(tx) > 0
        to_twd = lambda cur, amt: float(amt)
        buckets, _ = compute_income_statement(tx, to_twd)
        total = sum(abs(v) for v in buckets.values())
        assert total > 0


class TestBankStatement:
    """Bank statement with transactions + deposits + loan."""

    @pytest.fixture
    def cfg(self):
        return load_config(str(EXAMPLES / "config_mid_career_family.yaml"))

    @pytest.fixture
    def parsed(self, cfg):
        return parse_single_md(EXAMPLES / "sample_bank_statement.md",
                               category_rules=cfg["category_rules"])

    def test_transactions_extracted(self, parsed):
        tx, _ = parsed
        assert len(tx) == 15

    def test_assets_extracted(self, parsed):
        _, assets = parsed
        assert len(assets) >= 1  # at least the USD deposit

    def test_salary_classified(self, parsed, cfg):
        tx, _ = parsed
        to_twd = make_fx(cfg["fx_rates"])
        buckets, classified = compute_income_statement(tx, to_twd)
        assert buckets[IS_SALARY] == 130000  # 65k + 65k

    def test_mortgage_split(self, parsed, cfg):
        """Mortgage auto-splits into principal and interest."""
        tx, _ = parsed
        to_twd = make_fx(cfg["fx_rates"])
        buckets, _ = compute_income_statement(tx, to_twd)
        assert buckets[IS_PRINCIPAL] == -12500
        assert buckets[IS_INTEREST] == -8200

    def test_internal_transfers_excluded(self, parsed, cfg):
        """Card payment and self-transfers should be excluded from IS."""
        tx, _ = parsed
        to_twd = make_fx(cfg["fx_rates"])
        _, classified = compute_income_statement(tx, to_twd)
        descs = [t["description"] for t in classified]
        # 永豐卡費 should be excluded (card payment)
        assert not any("卡費" in d for d in descs)
        # 自行轉帳 should be excluded
        assert not any("自行轉帳" in d for d in descs)


class TestCreditCardStatement:
    """Credit card statement with sign flip and exclusions."""

    @pytest.fixture
    def cfg(self):
        return load_config(str(EXAMPLES / "config_mid_career_family.yaml"))

    @pytest.fixture
    def parsed(self, cfg):
        return parse_single_md(EXAMPLES / "sample_credit_card.md",
                               category_rules=cfg["category_rules"])

    def test_transactions_extracted(self, parsed):
        tx, _ = parsed
        assert len(tx) == 25

    def test_amounts_sign_flipped(self, parsed):
        """Credit card amounts should be negative (expenses)."""
        tx, _ = parsed
        expenses = [t for t in tx if t["amount"] < 0]
        # Most items should be negative (expenses), some may be credits
        assert len(expenses) >= 20

    def test_auto_payment_excluded(self, parsed, cfg):
        """自扣已入帳 should be classified as internal_transfer via config rules."""
        tx, _ = parsed
        to_twd = make_fx(cfg["fx_rates"])
        _, classified = compute_income_statement(tx, to_twd)
        descs = [t["description"] for t in classified]
        assert not any("自扣已入帳" in d for d in descs)

    def test_cashback_excluded(self, parsed, cfg):
        """回饋入帳 should be classified as internal_transfer via config rules."""
        tx, _ = parsed
        to_twd = make_fx(cfg["fx_rates"])
        _, classified = compute_income_statement(tx, to_twd)
        descs = [t["description"] for t in classified]
        assert not any("回饋入帳" in d for d in descs)


class TestSecuritiesStatement:
    """Securities statement with stock holdings (assets only)."""

    @pytest.fixture
    def parsed(self):
        return parse_single_md(EXAMPLES / "sample_securities.md")

    def test_no_transactions(self, parsed):
        tx, _ = parsed
        assert len(tx) == 0

    def test_assets_extracted(self, parsed):
        _, assets = parsed
        assert len(assets) == 5

    def test_all_equities(self, parsed):
        _, assets = parsed
        for a in assets:
            assert a["category"] == "Equity"

    def test_known_holdings(self, parsed):
        _, assets = parsed
        names = {a["name"] for a in assets}
        assert "0050 元大台灣50" in names
        assert "2330 台積電" in names

    def test_subtotal_excluded(self, parsed):
        """小計 row should not appear as an asset."""
        _, assets = parsed
        names = {a["name"] for a in assets}
        assert "小計" not in names

    def test_market_values_correct(self, parsed):
        _, assets = parsed
        tsmc = [a for a in assets if "2330" in a["name"]][0]
        assert tsmc["amount"] == 190000  # 200 shares × 950


class TestCombinedPipeline:
    """All three statements combined — realistic monthly audit."""

    @pytest.fixture
    def cfg(self):
        return load_config(str(EXAMPLES / "config_mid_career_family.yaml"))

    @pytest.fixture
    def all_data(self, cfg):
        all_tx = []
        all_assets = []
        for f in ["sample_bank_statement.md", "sample_credit_card.md",
                   "sample_securities.md"]:
            tx, assets = parse_single_md(
                EXAMPLES / f, category_rules=cfg["category_rules"])
            all_tx.extend(tx)
            all_assets.extend(assets)
        return all_tx, all_assets

    def test_total_transactions(self, all_data):
        tx, _ = all_data
        assert len(tx) == 40  # 15 bank + 25 CC

    def test_total_assets(self, all_data):
        _, assets = all_data
        assert len(assets) == 7  # 5 equities + 1 USD deposit + 1 loan

    def test_positive_net_income(self, all_data, cfg):
        tx, _ = all_data
        to_twd = make_fx(cfg["fx_rates"])
        buckets, _ = compute_income_statement(tx, to_twd)
        cf = compute_cash_flow(buckets)
        # Dual-income family should have positive cash flow
        assert cf["net_flow"] > 0

    def test_balance_sheet_with_manual(self, all_data, cfg):
        _, assets = all_data
        to_twd = make_fx(cfg["fx_rates"])
        bs = compute_balance_sheet(assets, cfg["manual_assets"], to_twd)
        # Should have real estate from manual_assets
        assert bs["risk_buckets"]["real_estate"] == 25000000
        # Should have equities from securities
        assert bs["risk_buckets"]["equities"] > 600000

    def test_savings_rate(self, all_data, cfg):
        tx, _ = all_data
        to_twd = make_fx(cfg["fx_rates"])
        buckets, _ = compute_income_statement(tx, to_twd)
        cf = compute_cash_flow(buckets)
        income = cf["inflow"]
        savings_rate = cf["net_flow"] / income if income > 0 else 0
        # Mid-career family should save 30-60%
        assert 0.3 <= savings_rate <= 0.7

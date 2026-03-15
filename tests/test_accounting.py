"""Tests for accounting engine — classification, IS, BS, cash flow."""

import pytest
from personal_cfo.accounting import (
    _classify_tx, compute_income_statement, compute_balance_sheet,
    compute_cash_flow, IS_SALARY, IS_INVEST_INCOME, IS_CAPEX,
    IS_CAPITAL, IS_PRINCIPAL, IS_INTEREST, IS_FEES, IS_LIVING,
)


# ---------- _classify_tx: user overrides ----------

class TestClassifyUserOverrides:
    def test_internal_transfer_skipped(self):
        assert _classify_tx("anything", "internal_transfer", -5000) is None

    def test_ignore_skipped(self):
        assert _classify_tx("anything", "ignore", 1000) is None

    def test_salary_override(self):
        assert _classify_tx("mystery deposit", "salary", 150000) == IS_SALARY

    def test_income_override(self):
        assert _classify_tx("side gig", "income", 5000) == IS_SALARY

    def test_dividend_override(self):
        assert _classify_tx("anything", "dividend", 1000) == IS_INVEST_INCOME

    def test_interest_income_override(self):
        assert _classify_tx("bank stuff", "interest_income", 200) == IS_INVEST_INCOME

    def test_rental_income_override(self):
        """Bug fix: rental_income was missing from user override list."""
        assert _classify_tx("tenant payment", "rental_income", 30000) == IS_INVEST_INCOME

    def test_capex_override(self):
        assert _classify_tx("renovation", "capex", -500000) == IS_CAPEX

    def test_principal_override(self):
        assert _classify_tx("loan", "principal", -10000) == IS_PRINCIPAL

    def test_capital_transfer_override(self):
        assert _classify_tx("fund", "capital_transfer", -50000) == IS_CAPITAL


# ---------- _classify_tx: built-in rules ----------

class TestClassifyBuiltinInflows:
    def test_salary_keyword(self):
        assert _classify_tx("薪資入帳", "", 150000) == IS_SALARY

    def test_dividend_keyword(self):
        assert _classify_tx("股利發放", "", 5000) == IS_INVEST_INCOME

    def test_interest_keyword(self):
        assert _classify_tx("活存利息", "", 200) == IS_INVEST_INCOME

    def test_investment_redemption(self):
        assert _classify_tx("贖回基金", "", 100000) == IS_CAPITAL

    def test_e_wallet_withdrawal_skipped(self):
        assert _classify_tx("街口支付提領", "", 1000) is None

    def test_transfer_in_skipped(self):
        assert _classify_tx("手機轉帳", "", 50000) is None

    def test_unknown_inflow_is_living(self):
        assert _classify_tx("unknown deposit", "", 3000) == IS_LIVING


class TestClassifyBuiltinOutflows:
    def test_mortgage_principal(self):
        """Housing keyword, no '息' → principal."""
        assert _classify_tx("房貸本金", "", -25000) == IS_PRINCIPAL

    def test_mortgage_interest_by_keyword(self):
        """Housing keyword + '息' → interest."""
        assert _classify_tx("房貸利息", "", -5000) == IS_INTEREST

    def test_mortgage_interest_category(self):
        """Bug fix: mortgage_interest category was not handled."""
        assert _classify_tx("monthly payment", "mortgage_interest", -5000) == IS_INTEREST

    def test_mortgage_interest_category_no_keyword(self):
        """mortgage_interest should work even without housing keywords in desc."""
        assert _classify_tx("random description", "mortgage_interest", -3000) == IS_INTEREST

    def test_housing_category_principal(self):
        assert _classify_tx("monthly payment", "housing", -20000) == IS_PRINCIPAL

    def test_housing_category_interest(self):
        assert _classify_tx("monthly 息 payment", "housing", -5000) == IS_INTEREST

    def test_renovation_is_capex(self):
        assert _classify_tx("裝潢費用", "", -300000) == IS_CAPEX

    def test_recurring_investment_is_capex(self):
        """定期定額 (DCA) goes to CapEx."""
        assert _classify_tx("定期定額扣款", "", -10000) == IS_CAPEX

    def test_periodic_investment_is_capex(self):
        assert _classify_tx("定時定額 ETF", "", -5000) == IS_CAPEX

    def test_one_off_purchase_is_capital(self):
        """Bug fix: one-off investment purchases go to Capital, not CapEx."""
        assert _classify_tx("交割款", "", -100000) == IS_CAPITAL

    def test_fund_purchase_is_capital(self):
        assert _classify_tx("申購基金", "", -50000) == IS_CAPITAL

    def test_card_payment_skipped(self):
        assert _classify_tx("信用卡卡費", "", -55000) is None

    def test_transfer_out_skipped(self):
        assert _classify_tx("轉出至帳戶", "", -10000) is None

    def test_insurance_is_living(self):
        assert _classify_tx("保險扣款", "", -8000) == IS_LIVING

    def test_unknown_outflow_is_living(self):
        assert _classify_tx("random purchase", "", -1500) == IS_LIVING

    def test_fee_keyword(self):
        assert _classify_tx("跨行手續費", "", -15) == IS_FEES

    def test_fee_category(self):
        assert _classify_tx("something", "fee", -100) == IS_FEES


# ---------- _classify_tx: internal transfers ----------

class TestClassifyInternalTransfers:
    @pytest.mark.parametrize("desc", [
        "換匯 USD→TWD", "開單定存", "解約定存", "轉綜活",
        "轉存單", "轉定存", "自行轉帳", "約定轉帳",
        "跨轉至永豐", "自扣已入帳",
    ])
    def test_internal_keywords_skip(self, desc):
        assert _classify_tx(desc, "", -10000) is None


# ---------- compute_income_statement ----------

class TestComputeIS:
    @pytest.fixture
    def sample_transactions(self):
        return [
            {"description": "Salary", "amount": 150000, "currency": "TWD",
             "category": "salary", "date": "2026-01-05", "account": "A"},
            {"description": "Dividend", "amount": 6000, "currency": "TWD",
             "category": "dividend", "date": "2026-01-18", "account": "B"},
            {"description": "Grocery", "amount": -3500, "currency": "TWD",
             "category": "", "date": "2026-01-10", "account": "A"},
            {"description": "Mortgage Payment", "amount": -25000, "currency": "TWD",
             "category": "housing", "date": "2026-01-10", "account": "A"},
            {"description": "CC Payment", "amount": -55000, "currency": "TWD",
             "category": "internal_transfer", "date": "2026-01-20", "account": "A"},
        ]

    def test_buckets_sum(self, sample_transactions):
        to_twd = lambda cur, amt: float(amt)
        buckets, _ = compute_income_statement(sample_transactions, to_twd)
        assert buckets[IS_SALARY] == 150000
        assert buckets[IS_INVEST_INCOME] == 6000
        assert buckets[IS_LIVING] == -3500
        assert buckets[IS_PRINCIPAL] == -25000

    def test_internal_transfer_excluded(self, sample_transactions):
        to_twd = lambda cur, amt: float(amt)
        _, classified = compute_income_statement(sample_transactions, to_twd)
        descs = [t["description"] for t in classified]
        assert "CC Payment" not in descs

    def test_fx_conversion(self):
        tx = [{"description": "Dividend", "amount": 100, "currency": "USD",
               "category": "dividend", "date": "2026-01-01", "account": "A"}]
        to_twd = lambda cur, amt: float(amt) * 32.0 if cur == "USD" else float(amt)
        buckets, _ = compute_income_statement(tx, to_twd)
        assert buckets[IS_INVEST_INCOME] == pytest.approx(3200.0)


# ---------- compute_balance_sheet ----------

class TestComputeBS:
    def test_basic_balance_sheet(self):
        assets = [
            {"name": "Checking", "category": "Cash", "amount": 1000000, "currency": "TWD"},
            {"name": "ETF", "category": "Equity", "amount": 500000, "currency": "TWD"},
            {"name": "Mortgage", "category": "Loan", "amount": -5000000, "currency": "TWD"},
        ]
        to_twd = lambda cur, amt: float(amt)
        bs = compute_balance_sheet(assets, [], to_twd)
        assert bs["risk_buckets"]["liquid_cash"] == 1000000
        assert bs["risk_buckets"]["equities"] == 500000
        assert bs["total_liabilities"] == 5000000
        assert bs["net_worth"] == 1500000 - 5000000

    def test_manual_assets_added(self):
        manual = [{"name": "House", "category": "Real Estate",
                   "amount": 30000000, "currency": "TWD"}]
        to_twd = lambda cur, amt: float(amt)
        bs = compute_balance_sheet([], manual, to_twd)
        assert bs["risk_buckets"]["real_estate"] == 30000000


# ---------- compute_cash_flow ----------

class TestComputeCashFlow:
    def test_excludes_capital_and_capex(self):
        buckets = {
            IS_SALARY: 150000,
            IS_INVEST_INCOME: 6000,
            IS_CAPITAL: -100000,
            IS_LIVING: -80000,
            IS_CAPEX: -50000,
            IS_PRINCIPAL: -25000,
            IS_INTEREST: -5000,
            IS_FEES: -200,
        }
        cf = compute_cash_flow(buckets)
        assert cf["inflow"] == 156000
        assert cf["outflow"] == -110200
        assert cf["net_flow"] == pytest.approx(45800)

"""Tests for _parse_assets_from_tables — asset extraction from pipe tables."""

import pytest
from personal_cfo.parser import _parse_assets_from_tables


class TestSecuritiesTable:
    def test_extracts_stock_holdings(self):
        md = """\
| 交易別 | 證券 | 庫存餘額 | 平均成本價格 | 總投資成本 | 參考市價 | 參考市値 | 未實現投資損益 (不含息) |
| -------- | ----------- | -------- | -------- | -------- | -------- | -------- | -------- |
|          |             |          |          |          |          |          |          |
| 現股 | 0050 元大台灣50 | 1,000 | 155.00 | 155,000 | 181.15 | 181,150 | 26,150 |
| 現股 | 2330 台積電 | 200 | 580.00 | 116,000 | 950.00 | 190,000 | 74,000 |
|  | 小計 | 1,200 |  | 271,000 |  | 371,150 | 100,150 |
"""
        assets = _parse_assets_from_tables(md, vendor="Broker")
        assert len(assets) == 2  # 小計 excluded
        assert assets[0].name == "0050 元大台灣50"
        assert assets[0].amount == 181150  # market value
        assert assets[0].category == "Equity"
        assert assets[1].name == "2330 台積電"
        assert assets[1].amount == 190000

    def test_skips_subtotals(self):
        md = """\
| 交易別 | 證券 | 庫存餘額 | 參考市値 |
| -------- | ----------- | -------- | -------- |
| 現股 | 0050 元大台灣50 | 1,000 | 181,150 |
|  | 小計 | 1,000 | 181,150 |
|  | 合計 | 1,000 | 181,150 |
"""
        assets = _parse_assets_from_tables(md)
        assert len(assets) == 1


class TestDepositTable:
    def test_extracts_deposits(self):
        md = """\
| 幣別 | 存款種類 | 帳號 | 臺幣餘額 |
| --- | -------- | --- | ------ |
| 新臺幣 | 活期儲蓄存款 | 001-XXX | 285,680 |
| 新臺幣 | 綜存定期存款 | 001-XXX | 500,000 |
"""
        assets = _parse_assets_from_tables(md, vendor="Bank")
        assert len(assets) == 2
        assert assets[0].category == "Cash"
        assert assets[0].amount == 285680
        assert assets[1].category == "Fixed Deposit"
        assert assets[1].amount == 500000

    def test_foreign_currency_deposit(self):
        md = """\
| 幣別 | 存款種類 | 帳號 | 外幣餘額 |
| --- | -------- | --- | ------ |
| 美元 | 外幣組合存款 | 001-XXX | 5,000.00 |
"""
        assets = _parse_assets_from_tables(md, vendor="Bank")
        assert len(assets) == 1
        assert assets[0].amount == 5000.0


class TestLoanTable:
    def test_extracts_loans_as_negative(self):
        md = """\
| 帳號 | 貸款種類 | 貸款餘額 | 利率 |
| --- | --- | --- | --- |
| 001-XXX | 房屋貸款 | 4,850,000 | 2.185% |
"""
        assets = _parse_assets_from_tables(md, vendor="Bank")
        assert len(assets) == 1
        assert assets[0].category == "Loan"
        assert assets[0].amount == -4850000  # negative


class TestTransactionTableExcluded:
    def test_ignores_transaction_tables(self):
        """Tables with 支出/存入 columns are transaction tables, not assets."""
        md = """\
| 日期 | 摘要 | 支出 | 存入 | 餘額 |
| --- | --- | --- | --- | --- |
| 2026/02/05 | Salary |  | 65,000 | 288,430 |
| 2026/02/10 | Rent | 30,000 |  | 258,430 |
"""
        assets = _parse_assets_from_tables(md)
        assert len(assets) == 0  # should NOT extract from transaction tables


class TestOverviewTable:
    def test_skips_deposit_items_in_overview(self):
        """Overview tables with 約當台幣 should skip deposit sub-items."""
        md = """\
| 項目 | 約當台幣 |
| --- | --- |
| 活期存款 | 500,000 |
| 定期存款 | 1,000,000 |
| 基金投資 | 300,000 |
"""
        assets = _parse_assets_from_tables(md)
        # Should skip 活期 and 定期 (deposits), keep 基金
        fund = [a for a in assets if "基金" in a.name]
        assert len(fund) == 1
        assert fund[0].amount == 300000

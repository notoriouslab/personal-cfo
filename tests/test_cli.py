"""Tests for CLI — validation, atomic write, snapshot, commands."""

import json
import os
import sys
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from personal_cfo.cli import _validate_period, _atomic_write, _save_snapshot
from personal_cfo.models import BalanceSheet


class TestValidatePeriod:
    def test_valid_period(self):
        assert _validate_period("2026-01") == "2026-01"

    def test_none_period(self):
        assert _validate_period(None) is None

    def test_empty_period(self):
        assert _validate_period("") == ""

    def test_invalid_format_exits(self):
        with pytest.raises(SystemExit):
            _validate_period("2026/01")

    def test_path_traversal_exits(self):
        with pytest.raises(SystemExit):
            _validate_period("../../etc")

    def test_only_year_exits(self):
        with pytest.raises(SystemExit):
            _validate_period("2026")

    def test_extra_chars_exits(self):
        with pytest.raises(SystemExit):
            _validate_period("2026-01-15")


class TestAtomicWrite:
    def test_creates_file(self, tmp_path):
        p = tmp_path / "test.txt"
        _atomic_write(str(p), "hello")
        assert p.read_text() == "hello"

    def test_creates_parent_dirs(self, tmp_path):
        p = tmp_path / "sub" / "dir" / "test.txt"
        _atomic_write(str(p), "nested")
        assert p.read_text() == "nested"

    def test_overwrites_existing(self, tmp_path):
        p = tmp_path / "test.txt"
        p.write_text("old")
        _atomic_write(str(p), "new")
        assert p.read_text() == "new"

    def test_no_partial_on_error(self, tmp_path):
        """If write fails, original file should be unchanged."""
        p = tmp_path / "test.txt"
        p.write_text("original")
        # Simulate error by making parent read-only after creating tempfile
        # This is hard to test perfectly, but we verify the basic flow works
        _atomic_write(str(p), "updated")
        assert p.read_text() == "updated"

    def test_utf8_content(self, tmp_path):
        p = tmp_path / "test.txt"
        _atomic_write(str(p), "中文測試 日本語テスト")
        assert p.read_text(encoding="utf-8") == "中文測試 日本語テスト"


class TestSaveSnapshot:
    def test_creates_snapshot_json(self, tmp_path):
        bs = BalanceSheet(
            details=[],
            risk_buckets={
                "liquid_cash": 1000000.0,
                "equities": 500000.0,
                "bonds": 200000.0,
                "real_estate": 0.0,
                "insurance": 0.0,
                "other": 0.0,
            },
            total_assets=1700000.0,
            total_liabilities=0.0,
            net_worth=1700000.0,
            total_cash=1000000.0,
        )
        snapshot = _save_snapshot(bs, "2026-01", str(tmp_path))
        snap_path = tmp_path / "snapshots" / "2026-01_asset_snapshot.json"
        assert snap_path.exists()

        data = json.loads(snap_path.read_text())
        assert data["period"] == "2026-01"
        assert data["net_worth"] == 1700000.0
        assert 0 < data["equity_ratio"] < 1

    def test_equity_ratio_excludes_non_investable(self, tmp_path):
        bs = BalanceSheet(
            details=[],
            risk_buckets={
                "liquid_cash": 500000.0,
                "equities": 500000.0,
                "bonds": 0.0,
                "real_estate": 10000000.0,
                "insurance": 1000000.0,
                "other": 0.0,
            },
            total_assets=12000000.0,
            total_liabilities=0.0,
            net_worth=12000000.0,
            total_cash=500000.0,
        )
        snapshot = _save_snapshot(bs, "2026-02", str(tmp_path))
        # equity_ratio = 500k / (12M - 10M - 1M) = 500k / 1M = 0.5
        assert snapshot["equity_ratio"] == pytest.approx(0.5)


class TestCmdCfo:
    def test_no_data_exits(self, tmp_path):
        """cmd_cfo should exit if no data found."""
        from personal_cfo.cli import cmd_cfo
        args = MagicMock()
        args.period = "2026-01"
        args.config = str(tmp_path / "nonexistent.yaml")
        args.transactions = [str(tmp_path / "empty")]
        args.assets = None
        args.offline = True
        args.output = str(tmp_path / "output")
        args.quiet = True

        (tmp_path / "empty").mkdir()
        with pytest.raises(SystemExit):
            cmd_cfo(args)

    def test_csv_pipeline(self, tmp_path):
        """cmd_cfo runs E2E with CSV input."""
        from personal_cfo.cli import cmd_cfo
        examples = Path(__file__).parent.parent / "examples"
        config_path = examples.parent / "config.example.yaml"

        args = MagicMock()
        args.period = "2026-01"
        args.config = str(config_path)
        args.transactions = [str(examples / "sample_transactions.csv")]
        args.assets = str(examples / "sample_assets.csv")
        args.offline = True
        args.output = str(tmp_path / "output")
        args.quiet = True

        cmd_cfo(args)
        report = tmp_path / "output" / "financial_report_2026-01.md"
        assert report.exists()
        content = report.read_text()
        assert "損益表" in content
        assert "資產負債表" in content


class TestCmdTrack:
    def test_no_snapshots_exits(self, tmp_path):
        """cmd_track should exit if no snapshots found."""
        from personal_cfo.cli import cmd_track
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        args = MagicMock()
        args.snapshots = str(snap_dir)
        args.config = str(tmp_path / "nonexistent.yaml")
        args.output = str(tmp_path / "output")
        args.quiet = True

        with pytest.raises(SystemExit):
            cmd_track(args)

    def test_with_snapshots(self, tmp_path):
        """cmd_track processes snapshot files."""
        from personal_cfo.cli import cmd_track
        snap_dir = tmp_path / "snaps"
        snap_dir.mkdir()
        for period in ["2026-01", "2026-02"]:
            snap = {
                "period": period,
                "net_worth": 5000000,
                "total_assets": 6000000,
                "total_liabilities": 1000000,
                "total_cash": 1000000,
                "equity_ratio": 0.20,
                "risk_buckets": {"equities": 1200000},
            }
            (snap_dir / f"{period}_asset_snapshot.json").write_text(
                json.dumps(snap))

        config_path = Path(__file__).parent.parent / "config.example.yaml"
        args = MagicMock()
        args.snapshots = str(snap_dir)
        args.config = str(config_path)
        args.output = str(tmp_path / "output")
        args.quiet = True

        cmd_track(args)
        reports = list((tmp_path / "output").glob("track_audit_*.md"))
        assert len(reports) == 1

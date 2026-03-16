"""Tests for config loader."""

import pytest
from personal_cfo.config import load_config


class TestLoadConfig:
    def test_defaults_when_no_file(self, tmp_path):
        cfg = load_config(str(tmp_path / "nonexistent.yaml"))
        assert cfg["life_plan"]["birth_year"] == 1980
        assert cfg["glide_path"]["equity_target"] == 0.60
        assert cfg["assumptions"]["base_currency"] == "TWD"

    def test_loads_example_config(self):
        """Ensure the shipped config.example.yaml is valid."""
        from pathlib import Path
        example = Path(__file__).parent.parent / "config.example.yaml"
        if example.exists():
            cfg = load_config(str(example))
            assert cfg["life_plan"]["birth_year"] == 1980
            assert len(cfg["category_rules"]) > 0

    def test_validates_birth_year(self, tmp_path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("life_plan:\n  birth_year: 1800\n")
        with pytest.raises(ValueError, match="birth_year"):
            load_config(str(cfg_file))

    def test_validates_equity_target(self, tmp_path):
        cfg_file = tmp_path / "bad.yaml"
        cfg_file.write_text("glide_path:\n  equity_target: 1.5\n")
        with pytest.raises(ValueError, match="equity_target"):
            load_config(str(cfg_file))

    def test_merges_user_overrides(self, tmp_path):
        cfg_file = tmp_path / "custom.yaml"
        cfg_file.write_text(
            "life_plan:\n"
            "  birth_year: 1990\n"
            "glide_path:\n"
            "  equity_target: 0.50\n"
        )
        cfg = load_config(str(cfg_file))
        assert cfg["life_plan"]["birth_year"] == 1990
        assert cfg["glide_path"]["equity_target"] == 0.50
        # Defaults preserved for unspecified keys
        assert cfg["glide_path"]["annual_derisking"] == 0.01


    def test_deep_merge_preserves_nested_defaults(self, tmp_path):
        """Partial glide_path override must not lose other defaults."""
        cfg_file = tmp_path / "partial.yaml"
        cfg_file.write_text("glide_path:\n  equity_target: 0.30\n")
        cfg = load_config(str(cfg_file))
        assert cfg["glide_path"]["equity_target"] == 0.30
        # These must survive the merge — previously they were wiped
        assert cfg["glide_path"]["annual_derisking"] == 0.01
        assert cfg["glide_path"]["min_equity_floor"] == 0.30
        assert cfg["glide_path"]["drift_tolerance"] == 0.03
        assert cfg["glide_path"]["drift_warning"] == 0.05

    def test_fx_non_twd_target_raises(self, tmp_path):
        """fx_rates with non-TWD target should raise at config load time."""
        cfg_file = tmp_path / "fx.yaml"
        cfg_file.write_text("fx_rates:\n  USD_JPY: 150\n  EUR_TWD: 35.0\n")
        with pytest.raises(ValueError, match="XXX_TWD"):
            load_config(str(cfg_file))


class TestExampleConfigs:
    """Validate all example scenario configs load without error."""

    @pytest.fixture(params=[
        "config_young_professional.yaml",
        "config_mid_career_family.yaml",
        "config_pre_retirement.yaml",
    ])
    def example_config(self, request):
        from pathlib import Path
        return Path(__file__).parent.parent / "examples" / request.param

    def test_example_config_valid(self, example_config):
        if example_config.exists():
            cfg = load_config(str(example_config))
            assert "life_plan" in cfg
            assert "glide_path" in cfg
            assert 0 < cfg["glide_path"]["equity_target"] <= 1.0

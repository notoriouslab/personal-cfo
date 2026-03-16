"""Configuration loader for personal-cfo."""

import os
import yaml


_DEFAULTS = {
    "life_plan": {
        "birth_year": 1980,
        "retirement_age": 65,
        "life_expectancy": 90,
        "expected_pension_monthly": 0,
    },
    "glide_path": {
        "equity_target": 0.60,
        "annual_derisking": 0.01,
        "min_equity_floor": 0.30,
        "drift_tolerance": 0.03,
        "drift_warning": 0.05,
    },
    "assumptions": {
        "monthly_expense": 60000,
        "base_currency": "TWD",
        "inflation_rate": 0.025,
        "annual_savings": 0,
    },
    "projection": {
        "expected_returns": {
            "equities": 0.07,
            "bonds": 0.015,
            "liquid_cash": 0.015,
            "insurance": 0.02,
            "other": 0.01,
        },
    },
    "manual_assets": [],
    "category_rules": {},
    "annual_expenses": [],
    "fx_rates": {"USD_TWD": 32.0, "JPY_TWD": 0.21},
}


def _deep_merge(base, override):
    """Recursively merge override into base. Lists and non-dicts are replaced."""
    result = dict(base)
    for key, val in override.items():
        if (key in result and isinstance(result[key], dict)
                and isinstance(val, dict)):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = val
    return result


def load_config(path=None):
    """Load config from YAML file, falling back to defaults.

    Uses deep merge: user only needs to specify the keys they want to override.
    For example, setting only `glide_path: { equity_target: 0.30 }` preserves
    all other glide_path defaults (annual_derisking, drift_tolerance, etc.).
    """
    cfg = dict(_DEFAULTS)

    if path is None:
        path = os.environ.get("PERSONAL_CFO_CONFIG", "config.yaml")

    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, user_cfg)

    # Validate critical fields
    lp = cfg["life_plan"]
    if not isinstance(lp["birth_year"], int):
        raise ValueError("birth_year must be an integer")
    if not (1940 <= lp["birth_year"] <= 2010):
        raise ValueError("birth_year must be between 1940-2010")

    gp = cfg["glide_path"]
    if not (0 < gp["equity_target"] <= 1.0):
        raise ValueError("equity_target must be between 0 and 1")

    # Validate projection fields
    le = lp.get("life_expectancy", 84)
    if not (50 <= le <= 120):
        raise ValueError("life_expectancy must be between 50-120")
    if le <= lp["retirement_age"]:
        raise ValueError("life_expectancy must be greater than retirement_age")

    inf = cfg["assumptions"].get("inflation_rate", 0.025)
    if not (0 <= inf <= 0.20):
        raise ValueError("inflation_rate must be between 0 and 0.20")

    er = cfg.get("projection", {}).get("expected_returns", {})
    for bucket, rate in er.items():
        if not (-0.10 <= rate <= 0.30):
            raise ValueError(
                f"expected_returns.{bucket} must be between -10% and 30%")

    # Validate fx_rates: only XXX_TWD format supported
    bad_keys = [k for k in cfg.get("fx_rates", {})
                if not k.upper().endswith("_TWD")]
    if bad_keys:
        raise ValueError(
            f"fx_rates keys must be in XXX_TWD format. "
            f"Invalid: {', '.join(bad_keys)}")

    return cfg

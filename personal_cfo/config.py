"""Configuration loader for personal-cfo."""

import os
import yaml


_DEFAULTS = {
    "life_plan": {"birth_year": 1980, "retirement_age": 65},
    "glide_path": {
        "equity_target": 0.20,
        "annual_derisking": 0.01,
        "min_equity_floor": 0.05,
        "drift_tolerance": 0.03,
        "drift_warning": 0.05,
    },
    "assumptions": {"monthly_expense": 100000, "base_currency": "TWD"},
    "manual_assets": [],
    "category_rules": {},
    "annual_expenses": [],
    "fx_rates": {"USD_TWD": 32.0, "JPY_TWD": 0.21},
}


def load_config(path=None):
    """Load config from YAML file, falling back to defaults."""
    cfg = dict(_DEFAULTS)

    if path is None:
        path = os.environ.get("PERSONAL_CFO_CONFIG", "config.yaml")

    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        for key in cfg:
            if key in user_cfg:
                if isinstance(cfg[key], dict) and isinstance(user_cfg[key], dict):
                    cfg[key] = {**cfg[key], **user_cfg[key]}
                else:
                    cfg[key] = user_cfg[key]

    # Validate critical fields
    lp = cfg["life_plan"]
    if not isinstance(lp["birth_year"], int):
        raise ValueError("birth_year must be an integer")
    if not (1940 <= lp["birth_year"] <= 2010):
        raise ValueError("birth_year must be between 1940-2010")

    gp = cfg["glide_path"]
    if not (0 < gp["equity_target"] <= 1.0):
        raise ValueError("equity_target must be between 0 and 1")

    return cfg

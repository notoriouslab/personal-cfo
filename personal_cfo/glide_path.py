"""Retirement glide path — age-aware equity target and drift diagnosis."""

from datetime import datetime


def get_age(birth_year):
    """Calculate current age from birth year."""
    return datetime.now().year - birth_year


def target_equity_ratio(age, cfg):
    """Calculate target equity ratio for a given age.

    Glide path formula:
        equity_target is anchored to baseline_year (default: current year).
        target = equity_target - (years_since_baseline × annual_derisking)
        floored at min_equity_floor

    This means equity_target is the target at baseline_year's age.
    Each year after that, the target drops by annual_derisking.
    """
    gp = cfg["glide_path"]
    lp = cfg["life_plan"]

    baseline_year = gp.get("baseline_year", datetime.now().year)
    baseline_age = baseline_year - lp["birth_year"]
    years_delta = max(0, age - baseline_age)
    target = gp["equity_target"] - (years_delta * gp["annual_derisking"])
    return max(target, gp["min_equity_floor"])


def diagnose_drift(actual_equity_ratio, cfg):
    """Diagnose drift between actual and target equity ratio.

    Returns dict with target, actual, drift, status, message.
    """
    gp = cfg["glide_path"]
    if "baseline_year" not in gp:
        import sys
        print("  NOTE: glide_path.baseline_year not set. "
              "Target will stay at equity_target until you set it.",
              file=sys.stderr)
    age = get_age(cfg["life_plan"]["birth_year"])
    target = target_equity_ratio(age, cfg)

    drift = actual_equity_ratio - target
    abs_drift = abs(drift)

    if abs_drift <= gp["drift_tolerance"]:
        status = "on_track"
        msg = "Equity allocation is within target range."
    elif abs_drift <= gp["drift_warning"]:
        status = "minor_drift"
        direction = "偏高" if drift > 0 else "偏低"
        msg = f"Equity allocation slightly off target ({direction})."
    else:
        status = "major_drift"
        direction = "偏高 (overweight equities)" if drift > 0 else "偏低 (underweight equities)"
        msg = f"Equity allocation significantly off target: {direction}."

    return {
        "age": age,
        "target": target,
        "actual": actual_equity_ratio,
        "drift": drift,
        "abs_drift": abs_drift,
        "status": status,
        "message": msg,
    }


def glide_path_table(cfg, from_age=None, to_age=None):
    """Generate a glide path table from from_age to to_age.

    Returns list of (age, target_ratio) tuples.
    """
    lp = cfg["life_plan"]
    if from_age is None:
        from_age = get_age(lp["birth_year"])
    if to_age is None:
        to_age = lp.get("retirement_age", 65) + 6

    table = []
    for age in range(from_age, to_age + 1):
        table.append((age, target_equity_ratio(age, cfg)))
    return table

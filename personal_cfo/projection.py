"""Retirement projection engine — assumption-based forward simulation.

This module projects net worth year-by-year from a snapshot to life expectancy,
applying assumed inflation to expenses and weighted expected returns to assets.

IMPORTANT: All outputs are based on assumptions, not predictions.
"""

from datetime import datetime
from typing import List, Tuple

from .models import ProjectionYear
from .glide_path import target_equity_ratio

# Real estate is illiquid — cannot be withdrawn for living expenses.
_ILLIQUID_BUCKETS = frozenset({"real_estate"})


def weighted_portfolio_return(risk_buckets: dict, expected_returns: dict) -> float:
    """Calculate weighted average return from current allocation.

    Only considers liquid buckets (excludes real_estate).
    Returns 0.0 if total liquid is zero.
    """
    total = 0.0
    weighted = 0.0
    for bucket, amount in risk_buckets.items():
        if bucket in _ILLIQUID_BUCKETS or amount <= 0:
            continue
        rate = expected_returns.get(bucket, 0.0)
        weighted += amount * rate
        total += amount
    return weighted / total if total > 0 else 0.0


def split_liquid_illiquid(risk_buckets: dict) -> Tuple[float, float]:
    """Split risk buckets into liquid vs illiquid totals.

    Liquid: everything except real_estate.
    Illiquid: real_estate.
    """
    liquid = 0.0
    illiquid = 0.0
    for bucket, amount in risk_buckets.items():
        if amount <= 0:
            continue
        if bucket in _ILLIQUID_BUCKETS:
            illiquid += amount
        else:
            liquid += amount
    return liquid, illiquid


def rebalance_buckets(liquid_total: float, age: int, cfg: dict) -> dict:
    """Rebalance liquid assets to glide path target for a given age.

    Uses target_equity_ratio() to determine equity allocation.
    Remainder split: 60% bonds, 40% cash (simple approximation).
    """
    eq_ratio = target_equity_ratio(age, cfg)
    eq_amount = liquid_total * eq_ratio
    remainder = liquid_total - eq_amount
    return {
        "equities": eq_amount,
        "bonds": remainder * 0.6,
        "liquid_cash": remainder * 0.4,
        "insurance": 0.0,
        "other": 0.0,
    }


def run_projection(snapshot: dict, cfg: dict) -> List[ProjectionYear]:
    """Run year-by-year projection from snapshot to life expectancy.

    Algorithm (annual granularity):
    - Accumulation: liquid grows by weighted_return + annual_savings
    - Retirement: liquid shrinks by withdrawal (inflation-adjusted expense)
    - Real estate appreciates separately, never liquidated
    - Annual rebalance to glide path target
    """
    lp = cfg["life_plan"]
    assume = cfg["assumptions"]
    proj = cfg.get("projection", {})
    er = proj.get("expected_returns", {})

    birth_year = lp["birth_year"]
    retirement_age = lp["retirement_age"]
    life_expectancy = lp.get("life_expectancy", 90)
    monthly_expense = assume["monthly_expense"]
    inflation = assume.get("inflation_rate", 0.025)
    annual_savings = assume.get("annual_savings", 0)
    annual_pension = lp.get("expected_pension_monthly", 0) * 12
    # Derive start year from snapshot period
    period = snapshot.get("period", "")
    if period and "-" in period:
        start_year = int(period.split("-")[0])
    else:
        start_year = datetime.now().year

    current_age = start_year - birth_year
    buckets = dict(snapshot.get("risk_buckets", {}))
    liquid, illiquid = split_liquid_illiquid(buckets)

    rows = []
    for age in range(current_age, life_expectancy + 1):
        year = birth_year + age
        phase = "accumulation" if age < retirement_age else "retirement"
        years_from_start = age - current_age

        # Inflation-adjusted annual expense
        annual_expense = monthly_expense * 12 * (1 + inflation) ** years_from_start

        # Weighted return on liquid assets only.
        # Real estate is held at static value — no compound appreciation.
        # Rationale: RE appreciation is speculative, illiquid, and shouldn't
        # inflate net worth projections. Users can update snapshots manually.
        liquid_buckets = {k: v for k, v in buckets.items()
                         if k not in _ILLIQUID_BUCKETS and v > 0}
        w_return = weighted_portfolio_return(liquid_buckets, er)
        liquid_gain = liquid * w_return
        illiquid_gain = 0.0  # static — no appreciation

        # Net flow
        # Accumulation: annual_savings is the NET amount after salary minus
        # all expenses (living + mortgage + insurance etc). Can be negative
        # if expenses exceed income. Does NOT draw from investment portfolio
        # unless negative — negative savings means the portfolio is subsidizing.
        if phase == "accumulation":
            net_flow = annual_savings
        else:
            # Retirement: withdraw expense, receive pension (not inflation-adjusted)
            net_flow = -annual_expense + annual_pension

        # Update
        liquid = liquid + liquid_gain + net_flow
        illiquid = illiquid + illiquid_gain
        depleted = liquid <= 0
        if depleted:
            liquid = 0.0

        net_worth = liquid + illiquid

        rows.append(ProjectionYear(
            age=age,
            year=year,
            phase=phase,
            liquid_assets=liquid,
            illiquid_assets=illiquid,
            annual_expense=annual_expense,
            weighted_return=w_return,
            liquid_gain=liquid_gain,
            illiquid_gain=illiquid_gain,
            net_flow=net_flow,
            net_worth=net_worth,
            depleted=depleted,
        ))

        # Rebalance liquid portion for next year (if not depleted)
        if not depleted and liquid > 0:
            buckets = rebalance_buckets(liquid, age + 1, cfg)
            buckets["real_estate"] = illiquid
        else:
            buckets = {"real_estate": illiquid}

    return rows


def projection_summary(rows: List[ProjectionYear], cfg: dict) -> dict:
    """Generate summary statistics from projection rows."""
    lp = cfg["life_plan"]
    retirement_age = lp["retirement_age"]
    life_expectancy = lp.get("life_expectancy", 90)

    current_age = rows[0].age if rows else 0
    years_to_retirement = max(0, retirement_age - current_age)
    years_in_retirement = life_expectancy - retirement_age

    # Find retirement year row
    retire_rows = [r for r in rows if r.phase == "retirement"]
    retire_expense_start = retire_rows[0].annual_expense if retire_rows else 0
    retire_expense_end = retire_rows[-1].annual_expense if retire_rows else 0

    # Find retirement start net worth
    retire_start_nw = 0.0
    retire_start_liquid = 0.0
    for r in rows:
        if r.age == retirement_age:
            retire_start_nw = r.net_worth
            retire_start_liquid = r.liquid_assets
            break

    # Check depletion
    depleted_age = None
    for r in rows:
        if r.depleted:
            depleted_age = r.age
            break

    final = rows[-1] if rows else None
    final_nw = final.net_worth if final else 0
    final_liquid = final.liquid_assets if final else 0

    # Sustainability assessment
    if depleted_age is not None:
        sustainability = "depleted"
    elif final_liquid < retire_expense_end * 5:
        sustainability = "at_risk"
    else:
        sustainability = "sustainable"

    # 4% Rule check (Bengen 1994 / Trinity Study):
    # Net expense = expense minus pension (pension covers part of the need)
    # Required corpus = net expense / 0.04
    annual_pension = lp.get("expected_pension_monthly", 0) * 12
    net_retire_expense = max(0, retire_expense_start - annual_pension)
    required_corpus_4pct = net_retire_expense / 0.04 if net_retire_expense > 0 else 0
    four_pct_ratio = (retire_start_liquid / required_corpus_4pct
                      if required_corpus_4pct > 0 else 0)

    return {
        "current_age": current_age,
        "years_to_retirement": years_to_retirement,
        "years_in_retirement": years_in_retirement,
        "retirement_year": current_age + years_to_retirement + lp["birth_year"],
        "retire_start_net_worth": retire_start_nw,
        "retire_start_liquid": retire_start_liquid,
        "retire_expense_start": retire_expense_start,
        "retire_expense_end": retire_expense_end,
        "depleted_age": depleted_age,
        "final_net_worth": final_nw,
        "final_liquid": final_liquid,
        "sustainability": sustainability,
        "required_corpus_4pct": required_corpus_4pct,
        "four_pct_ratio": four_pct_ratio,
    }

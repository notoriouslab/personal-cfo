"""Core data structures for personal-cfo."""

from dataclasses import dataclass, asdict


@dataclass
class Transaction:
    """A single financial transaction."""
    date: str
    description: str
    amount: float
    currency: str = "TWD"
    category: str = ""
    account: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Asset:
    """A single asset or liability entry."""
    name: str
    category: str
    amount: float
    currency: str = "TWD"
    vendor: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClassifiedTx:
    """A transaction classified into an IS bucket with TWD conversion."""
    date: str
    description: str
    amount_twd: float
    currency: str
    amount_orig: float
    account: str
    bucket: str


@dataclass
class BalanceSheet:
    """Balance sheet summary."""
    details: list
    risk_buckets: dict
    total_assets: float
    total_liabilities: float
    net_worth: float
    total_cash: float


@dataclass
class CashFlow:
    """Cash flow summary."""
    inflow: float
    outflow: float
    net_flow: float


@dataclass
class GlideDiagnosis:
    """Retirement glide path drift diagnosis."""
    age: int
    target: float
    actual: float
    drift: float
    abs_drift: float
    status: str  # "on_track" | "minor_drift" | "major_drift"
    message: str


@dataclass
class ProjectionYear:
    """One row of the retirement projection table."""
    age: int
    year: int
    phase: str               # "accumulation" | "retirement"
    liquid_assets: float     # liquid portion (excl. real estate)
    illiquid_assets: float   # real estate etc.
    annual_expense: float    # inflation-adjusted expense for this year
    weighted_return: float   # portfolio return rate for this year
    liquid_gain: float       # investment return on liquid assets only
    illiquid_gain: float     # appreciation on illiquid assets (real estate)
    net_flow: float          # +savings or -withdrawal
    net_worth: float         # end of year total
    depleted: bool           # True if liquid assets hit zero

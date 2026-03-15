"""Core data structures for personal-cfo."""

from dataclasses import dataclass, field, asdict
from typing import Optional


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
class Snapshot:
    """Monthly asset snapshot for track mode."""
    period: str
    net_worth: float
    total_assets: float
    total_liabilities: float
    total_cash: float
    equity_ratio: float
    risk_buckets: dict = field(default_factory=dict)
    glide_path: Optional[GlideDiagnosis] = None

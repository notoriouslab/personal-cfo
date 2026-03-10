"""Static exchange rate converter."""

import sys

_warned_currencies = set()


def make_fx(rates_config):
    """Create a converter function from config fx_rates dict.

    rates_config: {"USD_TWD": 32.0, "JPY_TWD": 0.21, ...}
    Returns: to_twd(currency, amount) function.
    """
    rates = {}
    for key, val in rates_config.items():
        parts = key.split("_")
        if len(parts) == 2:
            rates[parts[0].upper()] = float(val)

    def to_twd(currency, amount):
        cur = currency.upper().strip()
        if cur == "TWD":
            return float(amount)
        rate = rates.get(cur)
        if rate is None:
            if cur not in _warned_currencies:
                print(f"  WARNING: No exchange rate for {cur}→TWD in config. "
                      f"Using 1.0 (amount will be wrong by ~{cur} rate).",
                      file=sys.stderr)
                _warned_currencies.add(cur)
            rate = 1.0
        return float(amount) * rate

    return to_twd

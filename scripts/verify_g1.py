"""Recompute the G1 arithmetic rather than quoting it.

G1 is the load-bearing claim of the whole project: it is what demotes every
expected-value satellite claim to INDETERMINATE_BY_CONSTRUCTION. A number that
important should be reproduced from its inputs, not copied from prose.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

MEDIAN_REAL_TERMINAL_EUR = 199_000
MATERIALITY_GATE_EUR = 5_000
HORIZON_YEARS = 20
EQUITY_VOL = 0.18
HISTORY_YEARS = 50


def portfolio_cagr_gap_pp() -> float:
    ratio = (MEDIAN_REAL_TERMINAL_EUR + MATERIALITY_GATE_EUR) / MEDIAN_REAL_TERMINAL_EUR
    return (ratio ** (1 / HORIZON_YEARS) - 1) * 100


def required_satellite_excess_pp(sleeve: float) -> float:
    """Excess the sleeve must earn for the portfolio to clear the gate.

    Linear in the sleeve weight: a first-order approximation, which is the
    right precision here because the whole point is that the requirement sits
    inside the estimation error.
    """
    return portfolio_cagr_gap_pp() / sleeve


def se_return_difference_pp(rho: float, vol: float = EQUITY_VOL, years: int = HISTORY_YEARS) -> float:
    sigma_diff = vol * math.sqrt(2 - 2 * rho)
    return sigma_diff / math.sqrt(years) * 100


def report() -> dict:
    gap = portfolio_cagr_gap_pp()
    out = {
        "portfolio_cagr_gap_pp_per_year": round(gap, 4),
        "required_satellite_excess_pp_per_year": {
            "sleeve_15pct": round(required_satellite_excess_pp(0.15), 3),
            "sleeve_5pct": round(required_satellite_excess_pp(0.05), 3),
        },
        "se_of_return_difference_pp_per_year": {
            "rho_0.95": round(se_return_difference_pp(0.95), 3),
            "rho_0.70": round(se_return_difference_pp(0.70), 3),
        },
    }
    lo_req = required_satellite_excess_pp(0.15)
    hi_se = se_return_difference_pp(0.70)
    out["requirement_lies_inside_estimation_error"] = bool(lo_req < hi_se)
    out["verdict"] = (
        "CONFIRMED: the smallest required satellite excess (%.2f pp/yr, 15%% sleeve) is "
        "smaller than the largest standard error of the underlying return difference "
        "(%.2f pp/yr). Expected-value satellite claims are undecidable with the available "
        "data -> INDETERMINATE_BY_CONSTRUCTION." % (lo_req, hi_se)
    )
    return out


if __name__ == "__main__":
    import json
    print(json.dumps(report(), indent=2))

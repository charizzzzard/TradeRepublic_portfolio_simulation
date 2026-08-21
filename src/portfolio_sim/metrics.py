"""Outcome metrics.

Phase 2 forbids reporting a CAGR on DCA cashflows: with a contribution stream,
a CAGR computed from start and end value is not a return anyone earned. The
money-weighted return (XIRR) is the correct statistic and is what this module
provides.
"""
from __future__ import annotations

import numpy as np

PERCENTILES = (5, 10, 50, 90, 95)


def xirr_monthly(cashflows: np.ndarray, terminal: np.ndarray,
                 lo: float = -0.9999, hi: float = 10.0, iters: int = 200) -> np.ndarray:
    """Annualised money-weighted return, vectorised over paths.

    `cashflows[:, t]` is the amount PAID IN at month t (a positive number is an
    outflow from the investor). `terminal[:]` is received at month T.

    Solved by bisection on the annual rate. NPV is monotonically decreasing in
    the rate, so bisection is unconditionally stable here - a Newton step is
    not, because the NPV of a long contribution stream is very flat near the
    root.
    """
    cashflows = np.asarray(cashflows, dtype=float)
    terminal = np.asarray(terminal, dtype=float)
    n_paths, T = cashflows.shape
    months = np.arange(T)

    def npv(rate):
        monthly = (1.0 + rate[:, None]) ** (-months[None, :] / 12.0)
        return terminal * (1.0 + rate) ** (-T / 12.0) - (cashflows * monthly).sum(axis=1)

    a = np.full(n_paths, lo)
    b = np.full(n_paths, hi)
    for _ in range(iters):
        mid = 0.5 * (a + b)
        v = npv(mid)
        too_high = v < 0.0
        b = np.where(too_high, mid, b)
        a = np.where(too_high, a, mid)
    return 0.5 * (a + b)


def max_drawdown(value_path: np.ndarray) -> np.ndarray:
    """Maximum peak-to-trough drawdown of each path, as a positive fraction.

    Computed on the portfolio VALUE path. With ongoing contributions the value
    path is not a return index, so this is the drawdown of wealth as the
    investor experiences it, which is the quantity the Phase 6 downside gate is
    defined on.
    """
    peak = np.maximum.accumulate(value_path, axis=1)
    dd = np.divide(peak - value_path, peak, out=np.zeros_like(value_path), where=peak > 0)
    return dd.max(axis=1)


def summary(values: np.ndarray) -> dict:
    values = np.asarray(values, dtype=float)
    out = {f"p{p}": float(np.percentile(values, p)) for p in PERCENTILES}
    out["mean"] = float(values.mean())
    out["median"] = out["p50"]
    return out


def prob_model(condition: np.ndarray, n_parameter_worlds: int, n_paths_per_world: int) -> dict:
    """A probability under the model, annotated as G4/G5 require.

    Never returns a bare float: every probability this project emits is
    P_model(... | model, parameter prior) and must carry its effective n.
    """
    condition = np.asarray(condition, dtype=bool)
    return {
        "P_model": float(condition.mean()),
        "n_parameter_worlds": int(n_parameter_worlds),
        "n_paths_per_world": int(n_paths_per_world),
        "effective_n_for_parameter_claims": int(n_parameter_worlds),
        "note": "G4: P_model(X) = P(X | model, parameter prior). Not a statement about the world. "
                "G5: for parameter-level claims the effective n is n_parameter_worlds, not the path count.",
    }


def win_rate_se(p: float, n_paths_per_world: int) -> float:
    """Standard error of a win rate, used to size the Phase 6 path budget."""
    return float(np.sqrt(p * (1.0 - p) / n_paths_per_world))

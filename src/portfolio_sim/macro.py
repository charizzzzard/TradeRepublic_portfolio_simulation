"""Inflation and the short rate, and the Basiszins derived from the short rate.

B.2 is the reason this module exists. Modelling the Basiszins deterministically
while the interest-rate world is stochastic is internally inconsistent: an
inflation regime without a rising Basiszins systematically UNDERSTATES the tax
burden, because the Vorabpauschale is proportional to the Basiszins.

Both processes are mean-reverting (Ornstein-Uhlenbeck, discretised monthly) and
are driven by the shared CRN block, so the tax world and the asset world move
together inside a given path.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MacroParams:
    inflation_mean: float = 0.02
    inflation_vol: float = 0.010
    inflation_kappa: float = 0.30
    inflation_start: float = 0.02

    short_rate_mean: float = 0.02
    short_rate_vol: float = 0.012
    short_rate_kappa: float = 0.25
    short_rate_start: float = 0.02

    # Pass-through from inflation to the short rate: a central-bank reaction.
    # This is what prevents a high-inflation path from carrying a zero Basiszins.
    inflation_passthrough: float = 0.80


def simulate_macro(params: MacroParams, crn, n_months: int) -> dict[str, np.ndarray]:
    """Simulate monthly inflation and short rate.

    Returns arrays of shape (n_paths, n_months) plus a cumulative price index of
    shape (n_paths, n_months + 1) starting at 1.0, used for real-terms
    deflation.
    """
    dt = 1.0 / 12.0
    zi = crn.macro("inflation")[:, :n_months]
    zr = crn.macro("short_rate")[:, :n_months]
    n_paths = zi.shape[0]

    inflation = np.empty((n_paths, n_months))
    short_rate = np.empty((n_paths, n_months))

    infl = np.full(n_paths, params.inflation_start)
    rate = np.full(n_paths, params.short_rate_start)
    sqrt_dt = np.sqrt(dt)

    for m in range(n_months):
        infl = (
            infl
            + params.inflation_kappa * (params.inflation_mean - infl) * dt
            + params.inflation_vol * sqrt_dt * zi[:, m]
        )
        # The short rate reverts to a target that itself moves with inflation.
        target = params.short_rate_mean + params.inflation_passthrough * (infl - params.inflation_mean)
        rate = (
            rate
            + params.short_rate_kappa * (target - rate) * dt
            + params.short_rate_vol * sqrt_dt * zr[:, m]
        )
        inflation[:, m] = infl
        short_rate[:, m] = rate

    price_index = np.ones((n_paths, n_months + 1))
    np.cumprod(1.0 + inflation / 12.0, axis=1, out=price_index[:, 1:])
    return {"inflation": inflation, "short_rate": short_rate, "price_index": price_index}


def basiszins_for_years(short_rate: np.ndarray, tax_cfg: dict, n_years: int) -> np.ndarray:
    """Basiszins per calendar year, set at the start of the year, floored at 0.

    B.2: `model: f(modellierter Kurzfristzins), Floor 0`.
    Shape (n_paths, n_years).
    """
    cfg = tax_cfg["basiszins"]
    a = float(cfg.get("a", 0.0))
    b = float(cfg.get("b", 1.0))
    term_premium = float(cfg.get("term_premium", 0.0))
    floor = float(cfg.get("floor", 0.0))

    n_paths = short_rate.shape[0]
    out = np.empty((n_paths, n_years))
    for y in range(n_years):
        # "set_at: start_of_calendar_year" -> the rate prevailing entering year y.
        month = max(0, y * 12 - 1)
        out[:, y] = a + b * short_rate[:, month] + term_premium
    return np.maximum(out, floor)

"""Simulation engine.

One call simulates one portfolio in one parameter world, vectorised over paths.
Every portfolio in a world draws from the same CRNBlock, so comparisons are
paired by construction (A.5).

Timeline convention
-------------------
Prices are P[:, 0..T] with P[:, 0] = 100. A contribution in month t buys at
P[:, t]. Calendar year y spans months 12y .. 12y+11; its start-of-year price is
P[:, 12y] and its end-of-year price is P[:, 12(y+1)].

The Vorabpauschale for year y is deemed to accrue on the first working day of
year y+1, i.e. at month index 12(y+1), and is taxed against the FSA of year
y+1. For the final year this index equals T, which is exactly why
`terminal_sale_timing` changes the result: selling on the last trading day of
year H-1 lands BEFORE that accrual, selling on the first business day of year H
lands AFTER it. That is the mechanical origin of the G7 terminal-timing spread.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .costs import CostSpec, spec_for
from .macro import MacroParams, basiszins_for_years, simulate_macro
from .position import Position
from .rng import CRNBlock
from .tax_engine import FSA, TaxClass, abgeltungsteuer


@dataclass(frozen=True)
class AssetParams:
    """Per-asset return parameters.

    `g` is the annual GEOMETRIC target under the frozen return convention
    (A.5): it is the median annual log growth, not the arithmetic mean. No Ito
    correction is applied.
    """
    g: float
    vol: float


@dataclass(frozen=True)
class PortfolioSpec:
    name: str
    weights: dict[str, float]
    gold_tax_variant: str = "B3_assumed"

    def __post_init__(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights of {self.name} sum to {total}, not 1.0")


@dataclass(frozen=True)
class RunSpec:
    horizon_years: int = 20
    contribution_growth: float = 0.02
    fsa_eur: float = 1000.0
    church_rate: float = 0.0
    funding_convention: str = "D3"
    terminal_sale_timing: str = "first_business_day_y_plus_1"
    ter_delta_bp: float = 0.0
    rebalance: str = "annual_calendar"
    initial_eur: float = 13000.0
    monthly_contribution_eur: float = 500.0
    track_pretax: bool = True


def _prices(assets, params, crn, full_corr, T, cost_specs):
    """Gross price paths with monthly cost drag applied.

    Frozen convention (A.5):
        monthly_factor = exp(log1p(g)/12 + (vol/sqrt(12)) * z)
    """
    z = crn.correlated(assets, full_corr)[:, :T, :]
    n_paths = z.shape[0]
    out = {}
    for j, a in enumerate(assets):
        p = params[a]
        drift = np.log1p(p.g) / 12.0
        shock = (p.vol / np.sqrt(12.0)) * z[:, :, j]
        factors = np.exp(drift + shock) * cost_specs[a].monthly_drag_factor()
        path = np.empty((n_paths, T + 1))
        path[:, 0] = 100.0
        np.cumprod(factors, axis=1, out=path[:, 1:])
        path[:, 1:] *= 100.0
        out[a] = path
    return out


def simulate(
    portfolio: PortfolioSpec,
    asset_params: dict[str, AssetParams],
    full_corr: np.ndarray,
    crn: CRNBlock,
    run: RunSpec,
    tax_cfg: dict,
    costs_cfg: dict,
    macro_params: MacroParams = MacroParams(),
) -> dict:
    assets = tuple(portfolio.weights.keys())
    weights = np.array([portfolio.weights[a] for a in assets])
    T = run.horizon_years * 12
    n_paths = crn.n_paths

    cost_specs = {a: spec_for(a, costs_cfg, run.ter_delta_bp) for a in assets}
    prices = _prices(assets, asset_params, crn, full_corr, T, cost_specs)

    macro = simulate_macro(macro_params, crn, T)
    basiszins = basiszins_for_years(macro["short_rate"], tax_cfg, run.horizon_years + 1)

    def tax_class_for(a):
        if a == "GOLD":
            return TaxClass.gold(tax_cfg, portfolio.gold_tax_variant)
        return TaxClass.equity_fund(tax_cfg)

    # T monthly purchases, plus one rebalancing purchase per asset per year
    # boundary, plus headroom.
    max_lots = T + run.horizon_years + 4
    pos = {a: Position(n_paths, max_lots, tax_class_for(a)) for a in assets}
    fsa = FSA(run.fsa_eur, n_paths, tax_cfg["freistellungsauftrag"]["cap_tolerance_eur"])
    tf = tax_cfg["teilfreistellung"]
    vap_factor = tax_cfg["vorabpauschale"]["basisertrag_factor"]

    pending = np.zeros(n_paths)          # D3: unfunded tax, charged to future contributions
    external_cash = np.zeros(n_paths)    # D2: tax paid from outside the portfolio
    tax_paid = np.zeros(n_paths)
    contributions_nominal = np.zeros(n_paths)
    contribution_path = np.zeros((n_paths, T))
    contributions_deflated = np.zeros(n_paths)
    pretax_value = np.zeros((n_paths, T + 1)) if run.track_pretax else None
    value_path = np.zeros((n_paths, T + 1))
    price_index = macro["price_index"]

    for a in assets:
        pos[a].start_year(prices[a][:, 0])

    def portfolio_value(t):
        return sum(pos[a].market_value(prices[a][:, t]) for a in assets)

    def settle(obligation, t):
        """Route a tax obligation through the configured funding convention."""
        nonlocal pending, external_cash
        if run.funding_convention == "D2":
            external_cash += obligation
        elif run.funding_convention == "D3":
            pending += obligation
        elif run.funding_convention == "D1":
            _pro_rata_sale(obligation, t)
        else:
            raise ValueError(f"unknown funding_convention {run.funding_convention}")

    def _pro_rata_sale(obligation, t):
        """D1: raise cash by selling pro rata, grossed up for the tax it triggers."""
        need = obligation.copy()
        for _ in range(3):
            total = portfolio_value(t)
            frac = np.divide(need, total, out=np.zeros_like(need), where=total > 0)
            frac = np.clip(frac, 0.0, 1.0)
            extra = np.zeros(n_paths)
            for a in assets:
                probe = pos[a]
                shares_before = probe.shares.copy()
                accum_before = probe.accum_vap.copy()
                r = probe.realise(frac, prices[a][:, t], t)
                probe.shares[:] = shares_before
                probe.accum_vap[:] = accum_before
                rate = tf["equity_fund"] if probe.tax_class.name == "equity_fund" else probe.tax_class.teilfreistellung
                extra += abgeltungsteuer(np.maximum(r["gain"], 0.0) * (1.0 - rate), run.church_rate)
            need = obligation + extra
        total = portfolio_value(t)
        frac = np.clip(np.divide(need, total, out=np.zeros_like(need), where=total > 0), 0.0, 1.0)
        for a in assets:
            spec = cost_specs[a]
            r = pos[a].realise(frac, prices[a][:, t], t)
            taxable = fsa.apply(np.maximum(r["gain"], 0.0) * (1.0 - pos[a].tax_class.teilfreistellung))
            due = abgeltungsteuer(taxable, run.church_rate)
            tax_paid[...] = tax_paid + due
            _ = spec.sell_net_of_costs(r["proceeds"])

    def invest(gross, t):
        """Split `gross` across target weights and buy."""
        for a, w in zip(assets, weights):
            spec = cost_specs[a]
            pos[a].buy(spec.buy_net_of_costs(gross * w), prices[a][:, t], t)

    def accrue_vorabpauschale(year, t):
        """Year-end Vorabpauschale, taxed on the first working day of year+1."""
        gross = np.zeros(n_paths)
        for a in assets:
            p = pos[a]
            v = p.year_end_vorabpauschale(prices[a][:, t], basiszins[:, year], year * 12, vap_factor)
            p.register_taxed_vorabpauschale(v)
            gross += v * (1.0 - p.tax_class.teilfreistellung)
            p.start_year(prices[a][:, t])
        taxable = fsa.apply(gross)
        due = abgeltungsteuer(taxable, run.church_rate)
        tax_paid[...] = tax_paid + due
        settle(due, t)

    # ---- monthly loop ---------------------------------------------------
    for t in range(T):
        if t > 0 and t % 12 == 0:
            year = t // 12 - 1
            # The FSA is reset FIRST. The Vorabpauschale for year `year` is
            # deemed to accrue on the first working day of year `year + 1`, so
            # it belongs to the tax year that is starting now and must consume
            # THAT year's allowance - not the leftover of the year just ended.
            fsa.reset()
            accrue_vorabpauschale(year, t)
            if run.rebalance == "annual_calendar" and len(assets) > 1:
                _rebalance(pos, prices, assets, weights, t, cost_specs, fsa, fsa_apply=True,
                           church_rate=run.church_rate, tax_paid=tax_paid, settle=settle)

        gross = run.initial_eur if t == 0 else 0.0
        contribution = run.monthly_contribution_eur * (1.0 + run.contribution_growth) ** (t // 12)
        gross = gross + contribution
        gross = np.full(n_paths, float(gross))

        if run.funding_convention == "D3":
            # D3: the tax bill reduces the NEXT contribution(s).
            covered = np.minimum(pending, gross)
            gross = gross - covered
            pending = pending - covered

        contribution_path[:, t] = gross
        contributions_nominal += gross
        contributions_deflated += gross / price_index[:, t]
        invest(gross, t)

        value_path[:, t] = portfolio_value(t)
        if run.track_pretax:
            pretax_value[:, t] = value_path[:, t]

    # ---- terminal -------------------------------------------------------
    if run.terminal_sale_timing == "first_business_day_y_plus_1":
        # The sale and the final Vorabpauschale both fall in the new tax year
        # and therefore SHARE one allowance. Resetting again after the accrual
        # would hand the disposal a second Sparer-Pauschbetrag.
        fsa.reset()
        accrue_vorabpauschale(run.horizon_years - 1, T)
    elif run.terminal_sale_timing != "last_trading_day_y":
        raise ValueError(f"unknown terminal_sale_timing {run.terminal_sale_timing}")

    value_path[:, T] = portfolio_value(T)
    if run.track_pretax:
        pretax_value[:, T] = value_path[:, T]

    proceeds_net = np.zeros(n_paths)
    gross_proceeds = np.zeros(n_paths)
    for a in assets:
        spec = cost_specs[a]
        r = pos[a].realise(np.ones(n_paths), prices[a][:, T], T)
        taxable = fsa.apply(np.maximum(r["gain"], 0.0) * (1.0 - pos[a].tax_class.teilfreistellung))
        due = abgeltungsteuer(taxable, run.church_rate)
        tax_paid += due
        gross_proceeds += r["proceeds"]
        proceeds_net += spec.sell_net_of_costs(r["proceeds"]) - due

    # D3 leftovers and D2 external cash are settled against the terminal value
    # so that all conventions are compared on a like-for-like net basis.
    proceeds_net -= pending
    proceeds_net -= external_cash

    deflator = price_index[:, T]
    return {
        "terminal_nominal_after_tax": proceeds_net,
        "terminal_real_after_tax": proceeds_net / deflator,
        "terminal_nominal_pretax": gross_proceeds,
        "terminal_real_pretax": gross_proceeds / deflator,
        "contributions_nominal": contributions_nominal,
        "contribution_path": contribution_path,
        "contributions_real": contributions_deflated,
        "tax_paid_nominal": tax_paid,
        "value_path_nominal": value_path,
        "value_path_real": value_path / price_index[:, : T + 1],
        "price_index": price_index,
        "basiszins": basiszins,
        "n_paths": n_paths,
    }


def _rebalance(pos, prices, assets, weights, t, cost_specs, fsa, fsa_apply,
               church_rate, tax_paid, settle):
    """Annual calendar rebalancing back to target weights.

    Overweights are sold (realising taxable gains, funded per convention);
    the proceeds buy the underweights.
    """
    values = np.array([pos[a].market_value(prices[a][:, t]) for a in assets])
    total = values.sum(axis=0)
    targets = weights[:, None] * total[None, :]
    excess = np.maximum(values - targets, 0.0)

    cash = np.zeros_like(total)
    due_total = np.zeros_like(total)
    for j, a in enumerate(assets):
        frac = np.divide(excess[j], values[j], out=np.zeros_like(total), where=values[j] > 0)
        if not np.any(frac > 0):
            continue
        r = pos[a].realise(frac, prices[a][:, t], t)
        taxable = np.maximum(r["gain"], 0.0) * (1.0 - pos[a].tax_class.teilfreistellung)
        if fsa_apply:
            taxable = fsa.apply(taxable)
        due = abgeltungsteuer(taxable, church_rate)
        due_total += due
        cash += cost_specs[a].sell_net_of_costs(r["proceeds"])

    tax_paid[...] = tax_paid + due_total
    settle(due_total, t)

    shortfall = np.maximum(targets - values, 0.0)
    denom = shortfall.sum(axis=0)
    for j, a in enumerate(assets):
        share = np.divide(shortfall[j], denom, out=np.zeros_like(total), where=denom > 0)
        pos[a].buy(cost_specs[a].buy_net_of_costs(cash * share), prices[a][:, t], t)

"""Pre-tax regression - PASS_EXACT.

Phase 1's acceptance demands a pre-tax regression. Baseline v2 is not present
in this repository (see conventions.json -> supersedes), so a regression
against v2's numbers is impossible and is NOT claimed here.

What IS checkable without v2, and is what the original gate was actually for,
is the INVARIANT the regression was meant to protect: changing the tax
configuration must not perturb the pre-tax mechanics. Under funding convention
D2 the tax is paid from outside the portfolio, so the pre-tax path is by
construction independent of every tax parameter. If a tax change moves a
pre-tax number, the tax engine is leaking into the return engine.

Bit equality, not tolerance.
"""
import copy

import numpy as np

from portfolio_sim import config
from portfolio_sim.engine import AssetParams, PortfolioSpec, RunSpec, simulate
from portfolio_sim.rng import CRNBlock, full_corr_from

TAX = config.load("tax")
COSTS = config.load("costs")
SEED = config.load("conventions")["seed"]
PARAMS = {"CORE": AssetParams(g=0.055, vol=0.16), "GOLD": AssetParams(g=0.0, vol=0.15)}
CORR = full_corr_from({("CORE", "GOLD"): 0.10})

PRETAX_KEYS = ("terminal_nominal_pretax", "terminal_real_pretax",
               "contributions_nominal", "value_path_nominal")


def _run(tax_cfg=None, portfolio=None, **kw):
    crn = CRNBlock(SEED, 0, 300, 120)
    portfolio = portfolio or PortfolioSpec("CORE_100", {"CORE": 1.0})
    kw.setdefault("funding_convention", "D2")
    return simulate(portfolio, PARAMS, CORR, crn,
                    RunSpec(horizon_years=10, **kw), tax_cfg or TAX, COSTS)


def _assert_pretax_identical(a, b, what):
    for key in PRETAX_KEYS:
        assert np.array_equal(a[key], b[key]), f"{what} perturbed pre-tax {key}"


def test_fsa_does_not_move_the_pretax_path():
    base = _run(fsa_eur=1000.0)
    for fsa in (0.0, 2000.0):
        _assert_pretax_identical(base, _run(fsa_eur=fsa), f"FSA={fsa}")


def test_church_tax_does_not_move_the_pretax_path():
    base = _run(church_rate=0.0)
    for k in (0.08, 0.09):
        _assert_pretax_identical(base, _run(church_rate=k), f"church={k}")


def test_teilfreistellung_does_not_move_the_pretax_path():
    modified = copy.deepcopy(TAX)
    modified["teilfreistellung"]["equity_fund"] = 0.0
    _assert_pretax_identical(_run(), _run(tax_cfg=modified), "Teilfreistellung=0")


def test_basiszins_does_not_move_the_pretax_path():
    modified = copy.deepcopy(TAX)
    modified["basiszins"]["b"] = 5.0
    _assert_pretax_identical(_run(), _run(tax_cfg=modified), "Basiszins slope=5")


def test_gold_tax_variant_does_not_move_the_pretax_path():
    """B.3 requires both variants to be reported. They must differ ONLY after tax."""
    mixed = PortfolioSpec("CORE_GOLD_90_10", {"CORE": 0.90, "GOLD": 0.10}, "B3_assumed")
    alt = PortfolioSpec("CORE_GOLD_90_10", {"CORE": 0.90, "GOLD": 0.10}, "B3_alternative")
    a, b = _run(portfolio=mixed), _run(portfolio=alt)
    _assert_pretax_identical(a, b, "GOLD tax variant")
    # ... and they must actually differ after tax, or the variant is inert.
    assert not np.array_equal(a["terminal_real_after_tax"], b["terminal_real_after_tax"])


def test_terminal_timing_does_not_move_the_pretax_terminal_value():
    """Terminal timing is a TAX event. Gross proceeds must be untouched by it."""
    a = _run(terminal_sale_timing="last_trading_day_y")
    b = _run(terminal_sale_timing="first_business_day_y_plus_1")
    assert np.array_equal(a["terminal_nominal_pretax"], b["terminal_nominal_pretax"])


def test_b1_withholding_branch_does_not_touch_any_decision_path_result():
    """B.1: the branch is retained but must be inert on every decision path.

    Changing it must move nothing, because no decision-path instrument is
    direct_stocks.
    """
    modified = copy.deepcopy(TAX)
    modified["withholding_tax_credit"]["status"] = "NOT_IN_DECISION_PATH"
    modified["withholding_tax_credit"]["known_v2_defect"] = "MUTATED FOR TEST"
    a, b = _run(), _run(tax_cfg=modified)
    for key in PRETAX_KEYS + ("terminal_real_after_tax", "tax_paid_nominal"):
        assert np.array_equal(a[key], b[key]), f"B.1 branch leaked into {key}"

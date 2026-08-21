"""Determinism and CRN integrity.

Teil D: a reproducibility FAIL is an unconditional STOP. These checks are
PASS_EXACT - bit equality, not tolerance.
"""
import numpy as np

from portfolio_sim import config
from portfolio_sim.engine import AssetParams, PortfolioSpec, RunSpec, simulate
from portfolio_sim.hashing import sha256_obj
from portfolio_sim.rng import CRNBlock, full_corr_from, world_seed

TAX = config.load("tax")
COSTS = config.load("costs")
SEED = config.load("conventions")["seed"]

PARAMS = {"CORE": AssetParams(g=0.055, vol=0.16), "GOLD": AssetParams(g=0.0, vol=0.15)}
CORR = full_corr_from({("CORE", "GOLD"): 0.10})


def _run(portfolio, **kw):
    crn = CRNBlock(SEED, 0, 300, 120)
    return simulate(portfolio, PARAMS, CORR, crn,
                    RunSpec(horizon_years=10, **kw), TAX, COSTS)


def test_identical_runs_are_bit_identical():
    a = _run(PortfolioSpec("CORE_100", {"CORE": 1.0}))
    b = _run(PortfolioSpec("CORE_100", {"CORE": 1.0}))
    for key in ("terminal_nominal_after_tax", "terminal_real_after_tax",
                "terminal_nominal_pretax", "tax_paid_nominal", "value_path_nominal"):
        assert np.array_equal(a[key], b[key]), f"{key} not bit-identical across runs"


def test_result_hash_is_stable():
    a = _run(PortfolioSpec("CORE_100", {"CORE": 1.0}))
    b = _run(PortfolioSpec("CORE_100", {"CORE": 1.0}))
    h = lambda r: sha256_obj([float(x) for x in r["terminal_real_after_tax"]])
    assert h(a) == h(b)


def test_world_seed_is_independent_of_portfolio_and_path_count():
    assert world_seed(SEED, 7) == world_seed(SEED, 7)
    assert world_seed(SEED, 7) != world_seed(SEED, 8)


def test_crn_gives_every_portfolio_the_same_asset_stream():
    """A.5: CRN is mandatory. An asset must consume the same underlying stream
    no matter which portfolio it appears in, so comparisons are paired."""
    crn = CRNBlock(SEED, 0, 200, 60)
    corr = full_corr_from({("CORE", "GOLD"): 0.35})
    solo = crn.correlated(("CORE",), corr)
    pair = crn.correlated(("CORE", "GOLD"), corr)
    assert np.array_equal(solo[:, :, 0], pair[:, :, 0])
    # And the guarantee must hold for a NON-first asset too, which is exactly
    # what a per-portfolio sub-matrix would break.
    gold_solo = crn.correlated(("GOLD",), corr)
    assert np.array_equal(gold_solo[:, :, 0], pair[:, :, 1])


def test_duplicated_asset_gives_an_exactly_identical_portfolio():
    """CRN plumbing check: splitting one asset into two perfectly correlated
    halves of itself must reproduce the single-asset portfolio EXACTLY
    (tolerance 1e-8 EUR).

    This validates the CRN wiring, the full-universe factorisation and the
    rebalancing arithmetic together. It is NOT the Phase 5 Null C1 test, which
    is a separate, pre-registered run.
    """
    import copy

    crn = CRNBlock(SEED, 0, 300, 120)
    corr = full_corr_from({("CORE", "SP500"): 1.0})
    params = {"CORE": PARAMS["CORE"], "SP500": PARAMS["CORE"]}

    # SP500 carries a different TER, so equalise the cost side for the identity.
    costs2 = copy.deepcopy(COSTS)
    costs2["instruments"]["SP500"] = dict(costs2["instruments"]["CORE"])

    single = simulate(PortfolioSpec("CORE_100", {"CORE": 1.0}), params, corr, crn,
                      RunSpec(horizon_years=10), TAX, costs2)
    split = simulate(PortfolioSpec("CORE_SPLIT", {"CORE": 0.5, "SP500": 0.5}), params, corr, crn,
                     RunSpec(horizon_years=10), TAX, costs2)

    delta = np.abs(split["terminal_real_after_tax"] - single["terminal_real_after_tax"])
    assert delta.max() < 1e-8, f"max delta {delta.max():.3e} EUR - IMPLEMENTATION_BUG"

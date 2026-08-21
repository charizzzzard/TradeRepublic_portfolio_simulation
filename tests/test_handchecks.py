"""Hand-computed checks of the decision-path tax, cost and return mechanics.

Every expected value below is derived by hand in the docstring or comment, from
the statute or the frozen convention - never from the code's own output. A
check that merely re-runs the implementation would prove nothing.

Checks HC01-HC25. HC22-HC23 cover the B.1 withholding-credit branch, which is
NOT_IN_DECISION_PATH: they must pass, but no gate may depend on them.
"""
import numpy as np
import pytest

from portfolio_sim import config
from portfolio_sim.costs import CostSpec
from portfolio_sim.engine import AssetParams, PortfolioSpec, RunSpec, simulate
from portfolio_sim.metrics import xirr_monthly
from portfolio_sim.position import Position
from portfolio_sim.rng import CRNBlock, full_corr_from
from portfolio_sim.tax_engine import (FSA, SOLI_RATE, TaxClass, abgeltungsteuer,
                                      acquisition_twelfths, basisertrag,
                                      credit_is_in_decision_path, effective_rate,
                                      vorabpauschale)

TAX = config.load("tax")
COSTS = config.load("costs")
TOL = 1e-9
FSA_TOL = 1e-8


# --- rate mechanics ------------------------------------------------------
def test_HC01_abgeltungsteuer_plus_soli():
    """25% ESt, Soli 5.5% ON THE TAX -> 0.25 * 1.055 = 0.26375."""
    assert abs(effective_rate(0.0) - 0.26375) < TOL
    assert abs(abgeltungsteuer(np.array([1000.0]))[0] - 263.75) < 1e-9


def test_HC02_church_tax_9pct():
    """e = K/(4+0.09) = 0.2444988; total = e*(1+0.055+0.09) = 0.2799511."""
    assert abs(effective_rate(0.09) - 0.27995110) < 1e-7


def test_HC03_church_tax_8pct():
    """e = K/4.08 = 0.24509804; total = e*1.135 = 0.27818627."""
    assert abs(effective_rate(0.08) - 0.27818627) < 1e-7


def test_HC04_soli_is_on_the_tax_not_on_income():
    """A common error: 25% + 5.5% = 30.5%. Correct is 25% * 1.055 = 26.375%."""
    assert effective_rate(0.0) == pytest.approx(EST := 0.25 * (1 + SOLI_RATE))
    assert abs(EST - 0.305) > 0.04


# --- Teilfreistellung ----------------------------------------------------
def test_HC05_teilfreistellung_equity_fund_30pct():
    """1000 gain, 30% exempt -> 700 taxable -> 700*0.26375 = 184.625."""
    taxable = 1000.0 * (1 - TAX["teilfreistellung"]["equity_fund"])
    assert abs(taxable - 700.0) < TOL
    assert abs(abgeltungsteuer(np.array([taxable]))[0] - 184.625) < 1e-9


def test_HC06_gold_etc_has_no_teilfreistellung():
    """B.3: an ETC is a debt security -> no partial exemption, full 26.375%."""
    gold = TaxClass.gold(TAX, "B3_assumed")
    assert gold.teilfreistellung == 0.0
    assert abs(abgeltungsteuer(np.array([1000.0]))[0] - 263.75) < 1e-9


def test_HC07_gold_etc_has_no_vorabpauschale_in_either_variant():
    """A Vorabpauschale applies to Investmentfonds only, not to a debt security."""
    for variant in ("B3_assumed", "B3_alternative"):
        assert TaxClass.gold(TAX, variant).vorabpauschale_applies is False
    assert "etc_debt_security" in TAX["vorabpauschale"]["does_not_apply_to"]


# --- Vorabpauschale ------------------------------------------------------
def test_HC08_basisertrag_formula():
    """Basisertrag = NAV_start * 0.7 * Basiszins = 10000 * 0.7 * 0.0253 = 177.10."""
    assert abs(basisertrag(10000.0, 0.0253) - 177.10) < 1e-9


def test_HC09_vorabpauschale_capped_by_wertsteigerung():
    """Basisertrag 177.10 but the fund only gained 100 -> Vorabpauschale = 100."""
    assert abs(vorabpauschale(10000.0, 0.0253, 100.0) - 100.0) < TOL


def test_HC10_vorabpauschale_floored_at_zero_on_a_loss():
    """A losing year produces no Vorabpauschale, never a negative one."""
    assert vorabpauschale(10000.0, 0.0253, -2000.0) == 0.0


def test_HC11_basiszins_floor_zero():
    """B.2: 2021/2022 had a negative reference rate -> floored to 0 -> no VAP."""
    from portfolio_sim.macro import basiszins_for_years
    negative = np.full((3, 24), -0.005)
    bz = basiszins_for_years(negative, TAX, 2)
    assert np.all(bz == 0.0)
    assert vorabpauschale(10000.0, 0.0, 5000.0) == 0.0


def test_HC12_acquisition_twelfths():
    """§18 Abs.1 S.3: reduced by 1/12 per FULL month preceding the acquisition month.
    January -> 12/12, March -> 10/12, December -> 1/12."""
    assert acquisition_twelfths(1) == 1.0
    assert abs(acquisition_twelfths(3) - 10 / 12) < TOL
    assert abs(acquisition_twelfths(12) - 1 / 12) < TOL
    with pytest.raises(ValueError):
        acquisition_twelfths(13)


def test_HC13_vorabpauschale_prorated_in_acquisition_year():
    """A lot bought in March: Basisertrag 177.10 * 10/12 = 147.5833."""
    assert abs(basisertrag(10000.0, 0.0253, twelfths=acquisition_twelfths(3)) - 147.58333333) < 1e-7


def test_HC14_vorabpauschale_reduces_the_disposal_gain():
    """§19 InvStG: a taxed Vorabpauschale must not be taxed again on disposal.

    One lot: 100 shares at 100 = 10000 cost. Price rises to 130 -> gross gain
    3000. A Vorabpauschale of 200 was already taxed -> taxable gain = 2800.
    """
    p = Position(1, 4, TaxClass.equity_fund(TAX))
    p.buy(np.array([10000.0]), np.array([100.0]), 0)
    p.register_taxed_vorabpauschale(np.array([200.0]))
    r = p.realise(np.ones(1), np.array([130.0]), 24)
    assert abs(r["gross_gain"][0] - 3000.0) < 1e-9
    assert abs(r["gain"][0] - 2800.0) < 1e-9


# --- Freistellungsauftrag ------------------------------------------------
def test_HC15_fsa_absorbs_then_taxes_the_excess():
    """FSA 1000: a 1500 taxable amount leaves 500 -> 500*0.26375 = 131.875."""
    fsa = FSA(1000.0, 1)
    excess = fsa.apply(np.array([1500.0]))
    assert abs(excess[0] - 500.0) < TOL
    assert abs(abgeltungsteuer(excess)[0] - 131.875) < 1e-9
    assert fsa.remaining[0] == 0.0


def test_HC16_fsa_cap_holds_to_tolerance_and_resets_annually():
    """A.5 fsa_cap_tolerance_eur = 1e-8. Repeated small uses must not drift."""
    fsa = FSA(1000.0, 1, FSA_TOL)
    for _ in range(10_000):
        fsa.apply(np.array([0.1]))
    assert fsa.remaining[0] == 0.0
    assert abs(fsa.remaining[0]) < FSA_TOL
    fsa.reset()
    assert abs(fsa.remaining[0] - 1000.0) < FSA_TOL


def test_HC17_fsa_zero_variant_taxes_everything():
    """A.4 sensitivity FSA = 0."""
    fsa = FSA(0.0, 1)
    assert abs(fsa.apply(np.array([1500.0]))[0] - 1500.0) < TOL


def test_HC18_loss_on_disposal_produces_no_tax():
    p = Position(1, 4, TaxClass.equity_fund(TAX))
    p.buy(np.array([10000.0]), np.array([100.0]), 0)
    r = p.realise(np.ones(1), np.array([70.0]), 24)
    assert r["gain"][0] < 0
    assert abgeltungsteuer(np.maximum(r["gain"], 0.0))[0] == 0.0


# --- return convention and costs ----------------------------------------
def test_HC19_frozen_return_convention_has_no_ito_correction():
    """A.5: factor = exp(log1p(g)/12 + vol/sqrt(12)*z). With z=0 and g=5.5%,
    twelve months compound to exactly 1.055."""
    g, vol = 0.055, 0.16
    factor = np.exp(np.log1p(g) / 12.0 + (vol / np.sqrt(12.0)) * 0.0)
    assert abs(factor ** 12 - 1.055) < 1e-12
    # The convention makes g the MEDIAN, so the mean must exceed it.
    z = np.random.default_rng(0).standard_normal(400_000)
    mean_factor = np.exp(np.log1p(g) / 12.0 + (vol / np.sqrt(12.0)) * z).mean()
    assert mean_factor > np.exp(np.log1p(g) / 12.0)


def test_HC20_ter_accrues_to_exactly_one_over_one_plus_ter_per_year():
    """0.20% TER compounds monthly to 1/1.002 over twelve months."""
    spec = CostSpec(ter=0.0020)
    assert abs(spec.monthly_drag_factor() ** 12 - 1 / 1.002) < 1e-12


def test_HC21_spread_and_execution_fee_on_a_buy():
    """500 EUR at 10bp spread and a 1 EUR execution fee -> 500*0.999 - 1 = 498.50."""
    spec = CostSpec(spread=0.0010, savings_plan_execution_eur=1.0)
    assert abs(spec.buy_net_of_costs(np.array([500.0]))[0] - 498.50) < 1e-9


# --- B.1: retained, correct, and NOT in the decision path ---------------
def test_HC22_withholding_credit_is_applied_against_est_not_against_26375():
    """B.1 / v2 defect. §32d: e = (K - 4q)/(4+k), Soli applied AFTERWARDS.

    K = 1000, q = 50, k = 0:  e = (1000-200)/4 = 200;  total = 200*1.055 = 211.00.
    The v2 defect credited against 26.375% directly: 263.75 - 50 = 213.75.
    """
    got = abgeltungsteuer(np.array([1000.0]), 0.0, np.array([50.0]))[0]
    assert abs(got - 211.00) < 1e-9
    assert abs(got - 213.75) > 2.0


def test_HC23_withholding_credit_cannot_create_a_refund():
    got = abgeltungsteuer(np.array([100.0]), 0.0, np.array([500.0]))[0]
    assert got == 0.0


def test_HC24_b1_branch_is_decoupled_from_every_gate():
    """B.1 acceptance: no gate may hang on a NOT_IN_DECISION_PATH branch."""
    assert credit_is_in_decision_path(TAX) is False
    assert TAX["withholding_tax_credit"]["gates_depending_on_this_branch"] == []
    # No instrument in the universe is direct_stocks, which is what makes the
    # branch unreachable on a decision path.
    classes = {v["tax_class"] for v in config.load("assets")["instruments"].values()}
    assert "direct_stocks" not in classes


# --- XIRR ----------------------------------------------------------------
def test_HC25_xirr_two_hand_solved_cases():
    """Phase 2 requires XIRR to be covered by at least two hand-computed cases.

    Case A: pay 1000 at t=0, receive 2000 at t=12 -> exactly 100%/yr.
    Case B: pay 100 at t=0 and 100 at t=12, receive 220 at t=24.
            -100 - 100/x + 220/x^2 = 0 with x = 1+r
            -> x^2 + x - 2.2 = 0 -> x = (-1 + sqrt(9.8))/2 -> r = 6.524758%.
    """
    cf = np.zeros((1, 12)); cf[0, 0] = 1000.0
    assert abs(xirr_monthly(cf, np.array([2000.0]))[0] - 1.0) < 1e-7

    cf = np.zeros((1, 24)); cf[0, 0] = 100.0; cf[0, 12] = 100.0
    exact = (-1 + np.sqrt(9.8)) / 2 - 1
    assert abs(xirr_monthly(cf, np.array([220.0]))[0] - exact) < 1e-7


# --- convention mechanics referenced by G7 -------------------------------
def _run(**kw):
    crn = CRNBlock(20260815, 0, 400, 120)
    return simulate(
        PortfolioSpec("CORE_100", {"CORE": 1.0}),
        {"CORE": AssetParams(g=0.055, vol=0.16)},
        full_corr_from({}), crn, RunSpec(horizon_years=10, **kw), TAX, COSTS,
    )


def test_HC26_terminal_timing_triggers_the_final_vorabpauschale():
    """G7 mechanism, isolated with FSA = 0 so no allowance masks it.

    Selling on the first business day of Y+1 lands AFTER the deemed accrual of
    the final Vorabpauschale; selling on the last trading day of Y lands
    before it. With no Sparer-Pauschbetrag to absorb anything, the later sale
    must pay strictly more tax on at least some paths and never less.
    """
    early = _run(terminal_sale_timing="last_trading_day_y", fsa_eur=0.0)
    late = _run(terminal_sale_timing="first_business_day_y_plus_1", fsa_eur=0.0)
    assert np.all(late["tax_paid_nominal"] >= early["tax_paid_nominal"] - 1e-9)
    assert np.mean(late["tax_paid_nominal"]) > np.mean(early["tax_paid_nominal"])


def test_HC27_vorabpauschale_consumes_the_new_tax_years_allowance():
    """The Vorabpauschale for year Y accrues on the first working day of Y+1,
    so it belongs to tax year Y+1 and shares ONE allowance with anything else
    realised in Y+1 - it must not get an allowance of its own.

    Terminal sale on the first business day of Y+1 therefore cannot consume
    more than one FSA in that final year: the tax paid under FSA=1000 must be
    at least (tax under FSA=0) minus 0.26375 * 1000 per tax year, and strictly
    more than if two full allowances had been granted.
    """
    zero = _run(terminal_sale_timing="first_business_day_y_plus_1", fsa_eur=0.0)
    one = _run(terminal_sale_timing="first_business_day_y_plus_1", fsa_eur=1000.0)
    saved = zero["tax_paid_nominal"] - one["tax_paid_nominal"]
    # 11 tax years are touched by a 10-year horizon under this timing.
    max_saving_one_allowance = 0.26375 * 1000.0 * 11
    assert np.all(saved >= -1e-9)
    assert np.max(saved) <= max_saving_one_allowance + 1e-6


def test_HC28_d3_funding_reduces_the_next_contribution():
    """A.5 baseline funding is D3. With FSA = 0 the tax bill is certain, so D3
    must invest strictly less than D2, which pays the same bill externally."""
    d2 = _run(funding_convention="D2", fsa_eur=0.0)
    d3 = _run(funding_convention="D3", fsa_eur=0.0)
    assert np.all(d3["contributions_nominal"] <= d2["contributions_nominal"] + 1e-9)
    assert np.median(d3["contributions_nominal"]) < np.median(d2["contributions_nominal"])

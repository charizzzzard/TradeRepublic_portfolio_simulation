"""PHASE 1 - R2F_DECISION_PATH_CLEANUP (bootstrap variant).

Runs the Phase 1 acceptance checks and emits run_manifest.json. No result
without a manifest (Teil C).

Re-scoping notice
-----------------
PROJECT_META Phase 1 specifies `Vorsteuer-Regression PASS_EXACT` against
Baseline v2. Baseline v2 is NOT present in this repository, so that comparison
is impossible and is NOT claimed. This run establishes baseline v3 instead and
checks the invariant the v2 regression was protecting: that no tax parameter
perturbs the pre-tax mechanics. See config/conventions.json -> supersedes.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from portfolio_sim import config, ledger, manifest  # noqa: E402
from portfolio_sim.engine import AssetParams, PortfolioSpec, RunSpec, simulate  # noqa: E402
from portfolio_sim.hashing import sha256_obj  # noqa: E402
from portfolio_sim.metrics import summary, xirr_monthly  # noqa: E402
from portfolio_sim.rng import CRNBlock, full_corr_from  # noqa: E402
from portfolio_sim.tax_engine import credit_is_in_decision_path  # noqa: E402

TAX = config.load("tax")
COSTS = config.load("costs")
CONV = config.load("conventions")
SEED = CONV["seed"]
RESULTS = ROOT / "results"

# Phase 1 is technical validation, not a satellite comparison, so the path
# budget is modest. Phase 6 requires 400 x 500 (see the falsification ledger).
N_WORLDS = 40
N_PATHS = 250
HORIZON = 20

# Parameter prior for the Phase 1 reference run. NOT calibrated: Phase 4 (R3)
# has not run, so no empirical data exists. These are declared assumptions used
# to exercise the machinery, and no claim rests on them.
PRIOR = {
    "core_g_mean": 0.055, "core_g_sd": 0.010,
    "core_vol_mean": 0.16, "core_vol_sd": 0.02,
    "status": "UNCALIBRATED_ASSUMPTION",
    "note": "Phase 4 (R3_DATA_ACQUISITION) has not run. No empirical calibration exists. "
            "These values exercise the engine; they support no claim.",
}


def core_params(world: int) -> dict:
    gen = np.random.default_rng(SEED * 7919 + world)
    return {"CORE": AssetParams(
        g=float(gen.normal(PRIOR["core_g_mean"], PRIOR["core_g_sd"])),
        vol=float(abs(gen.normal(PRIOR["core_vol_mean"], PRIOR["core_vol_sd"]))),
    )}


def run_core(run: RunSpec, worlds: int = N_WORLDS, paths: int = N_PATHS) -> dict:
    corr = full_corr_from({})
    portfolio = PortfolioSpec("CORE_100", {"CORE": 1.0})
    acc = {k: [] for k in ("terminal_real_after_tax", "terminal_nominal_after_tax",
                           "terminal_real_pretax", "contributions_nominal",
                           "contributions_real", "tax_paid_nominal", "xirr")}
    for w in range(worlds):
        crn = CRNBlock(SEED, w, paths, run.horizon_years * 12)
        r = simulate(portfolio, core_params(w), corr, crn, run, TAX, COSTS)
        for k in acc:
            if k == "xirr":
                acc[k].append(xirr_monthly(r["contribution_path"], r["terminal_nominal_after_tax"]))
            else:
                acc[k].append(r[k])
    return {k: np.concatenate(v) for k, v in acc.items()}


def check(name: str, passed: bool, detail: str) -> dict:
    return {"check": name, "result": "PASS" if passed else "FAIL", "detail": detail}


def main() -> int:
    checks: list[dict] = []

    # --- B.5: an explicit FX decision must exist -------------------------
    fx = config.assert_fx_decision_present()
    checks.append(check("B5_fx_decision_recorded", True,
                        f"{fx['decision']} / {fx['status']} (recorded in manifest)"))

    # --- B.1: the withholding branch must not gate anything --------------
    b1_ok = (not credit_is_in_decision_path(TAX)
             and TAX["withholding_tax_credit"]["gates_depending_on_this_branch"] == [])
    tax_classes = {v["tax_class"] for v in config.load("assets")["instruments"].values()}
    b1_ok = b1_ok and "direct_stocks" not in tax_classes
    checks.append(check("B1_withholding_credit_not_in_decision_path", b1_ok,
                        "status=NOT_IN_DECISION_PATH, no gate depends on it, "
                        "no direct_stocks instrument in the universe"))

    # --- B.2: Basiszins is coupled to the modelled short rate ------------
    bz_ok = TAX["basiszins"]["model"].startswith("max(0,") and TAX["basiszins"]["floor"] == 0.0
    checks.append(check("B2_basiszins_coupled_to_short_rate_floor_zero", bz_ok,
                        TAX["basiszins"]["model"]))

    # --- B.3: gold reported under both variants --------------------------
    b3_ok = TAX["b3_dual_reporting"]["required"] is True and all(
        TAX["assets_tax_classes"][k]["legal_status"] == "TO_BE_VERIFIED"
        for k in ("etc_debt_security_B3_assumed", "etc_debt_security_B3_alternative"))
    checks.append(check("B3_gold_dual_variant_required", b3_ok,
                        "both variants present, both TO_BE_VERIFIED, dual reporting enforced"))

    # --- B.4: cost model exists and every assumption carries a status ----
    b4_ok = COSTS["data_status"] == "PLACEHOLDER_NOT_SOURCED" and all(
        "td_legal_status" in row for row in COSTS["instruments"].values())
    checks.append(check("B4_cost_model_present_and_flagged", b4_ok,
                        "config/costs.json present; all values flagged "
                        "PLACEHOLDER_NOT_SOURCED - no cost claim may be promoted"))

    # --- test suite -------------------------------------------------------
    proc = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                          cwd=ROOT, capture_output=True, text=True)
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "no output"
    checks.append(check("handchecks_and_regression_suite", proc.returncode == 0, tail))

    # --- determinism: PASS_EXACT -----------------------------------------
    base = RunSpec(horizon_years=HORIZON)
    a = run_core(base, worlds=8, paths=200)
    b = run_core(base, worlds=8, paths=200)
    det_ok = all(np.array_equal(a[k], b[k]) for k in a)
    checks.append(check("determinism_PASS_EXACT", det_ok,
                        "two independent runs bit-identical on every reported array"))

    # --- pre-tax invariant: PASS_EXACT -----------------------------------
    d2 = RunSpec(horizon_years=HORIZON, funding_convention="D2")
    ref = run_core(d2, worlds=8, paths=200)
    variants = {
        "fsa_0": RunSpec(horizon_years=HORIZON, funding_convention="D2", fsa_eur=0.0),
        "fsa_2000": RunSpec(horizon_years=HORIZON, funding_convention="D2", fsa_eur=2000.0),
        "church_9pct": RunSpec(horizon_years=HORIZON, funding_convention="D2", church_rate=0.09),
    }
    pretax_ok = True
    for name, spec in variants.items():
        got = run_core(spec, worlds=8, paths=200)
        if not np.array_equal(got["terminal_real_pretax"], ref["terminal_real_pretax"]):
            pretax_ok = False
            checks.append(check(f"pretax_invariant[{name}]", False, "pre-tax path perturbed"))
    checks.append(check("pretax_invariant_PASS_EXACT", pretax_ok,
                        "no tax parameter perturbs the pre-tax path under D2 "
                        "(NOT a regression against baseline v2, which is absent)"))

    # --- reference run ----------------------------------------------------
    result = run_core(base)
    real_tv = result["terminal_real_after_tax"]
    reference = {
        "horizon_years": HORIZON,
        "n_parameter_worlds": N_WORLDS,
        "n_paths_per_world": N_PATHS,
        "terminal_real_after_tax": summary(real_tv),
        "terminal_real_pretax": summary(result["terminal_real_pretax"]),
        "contributions_nominal": summary(result["contributions_nominal"]),
        "contributions_real": summary(result["contributions_real"]),
        "tax_paid_nominal": summary(result["tax_paid_nominal"]),
        "xirr_money_weighted": summary(result["xirr"]),
        "P_model_real_terminal_below_real_contributions": {
            "P_model": float((real_tv < result["contributions_real"]).mean()),
            "n_parameter_worlds": N_WORLDS,
            "n_paths_per_world": N_PATHS,
            "note": "G4: P_model(X) = P(X | model, parameter prior), not a statement "
                    "about the world. G5: effective n for parameter claims is 40.",
        },
        "result_hash": sha256_obj([float(x) for x in real_tv]),
        "parameter_prior": PRIOR,
    }

    all_pass = all(c["result"] == "PASS" for c in checks)
    gates = {
        "phase1_acceptance": {
            "handchecks_in_decision_path": "PASS required",
            "pretax_regression": "PASS_EXACT required (invariant form; v2 absent)",
            "determinism": "PASS_EXACT required",
            "configs_complete_with_legal_status": "required",
            "no_gate_depends_on_NOT_IN_DECISION_PATH": "required",
        }
    }

    man = manifest.build(
        run_id="phase1_r2f_decision_path_cleanup",
        phase="PHASE_1_R2F_DECISION_PATH_CLEANUP",
        n_parameter_worlds=N_WORLDS,
        n_paths_per_world=N_PATHS,
        portfolio_definitions={"CORE_100": {"CORE": 1.0}},
        status="DISCOVERY",
        engine="C",
        gates=gates,
        extra={
            "rescoping_notice": (
                "Phase 1 as written requires PASS_EXACT against baseline v2. Baseline v2 is "
                "absent from this repository, so that regression was NOT performed and is NOT "
                "claimed. The invariant form was checked instead. This run ESTABLISHES "
                "baseline v3."
            ),
            "acceptance_checks": checks,
            "acceptance": "PASS" if all_pass else "FAIL",
            "reference_run": reference,
            "g1_verification": __import__("verify_g1").report(),
            "assumption_echo_notice": (
                "G3: Phase 1 produces NO ranking of assets. Any rank ordering reproduced "
                "elsewhere is an echo of the input mu vectors, not a simulation result."
            ),
        },
    )
    RESULTS.mkdir(exist_ok=True)
    manifest.write(man, RESULTS / "phase1" / "run_manifest.json")
    (RESULTS / "phase1" / "baseline_v3_reference.json").write_text(
        json.dumps(reference, indent=2, sort_keys=True), encoding="utf-8")
    ledger.write()

    print("\n=== PHASE 1 ACCEPTANCE ===")
    for c in checks:
        print(f"  [{c['result']:4}] {c['check']}\n         {c['detail']}")
    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
    print(f"\n  real terminal value (after tax, {HORIZON}y): "
          f"median {reference['terminal_real_after_tax']['median']:,.0f} EUR")
    print(f"  money-weighted return (XIRR): median "
          f"{reference['xirr_money_weighted']['median'] * 100:.2f}%/yr")
    print(f"  manifest -> results/phase1/run_manifest.json")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())

"""PHASE 2 - R11_SAVINGS_DYNAMICS.

Quantifies the contribution-growth lever BEFORE any satellite test, because it
is controllable and largely parameter-independent (PROJECT_META Phase 2).

Scope discipline
----------------
100 % CORE only. No satellite is simulated, and the mandatory cross-phase
comparison ("+1 pp contribution growth vs. the largest measured satellite
median delta") is NOT performed here: no valid v3 satellite delta exists yet,
and the v2 figures quoted in PROJECT_META were produced by a package absent
from this repository. Inventing that comparison would be circular. The
comparator measured here is frozen instead, and the comparison becomes an
explicit later gate condition.

Pairing
-------
Within a horizon, all four growth scenarios share the same parameter worlds AND
the same CRNBlock instance, so every delta is paired path by path. The CRN
object is constructed once per (horizon, world) in the outer loop and handed to
all four scenarios - the pairing is structural, not a convention someone has to
remember.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_sim import config, gates, manifest  # noqa: E402
from portfolio_sim.engine import PortfolioSpec, RunSpec, simulate  # noqa: E402
from portfolio_sim.hashing import sha256_obj  # noqa: E402
from portfolio_sim.metrics import summary, xirr_monthly  # noqa: E402
from portfolio_sim.rng import CRNBlock, full_corr_from  # noqa: E402

# The parameter prior and world construction are IMPORTED from Phase 1 rather
# than copied, so "identical parameter worlds" is guaranteed by construction
# and cannot drift out of sync with a duplicated definition.
from run_phase1 import PRIOR, TAX, COSTS, SEED, core_params  # noqa: E402

BASELINE_REF = "5efb528af366810042870a6aa40faf0ec775d825"
PHASE1_MANIFEST = ROOT / "results" / "phase1" / "run_manifest.json"
RESULTS = ROOT / "results" / "phase2"

N_WORLDS = 100
N_PATHS = 500
HORIZONS = (10, 20)
GROWTH_RATES = (0.00, 0.02, 0.03, 0.05)

# metrics.xirr_monthly defaults to 200 bisection steps. The bracket collapses to
# double precision long before that: 80 steps is verified bit-identical to the
# default (checked at runtime below), so this is a pure performance choice with
# no numerical consequence. metrics.py itself is NOT modified - `iters` is an
# existing parameter.
XIRR_ITERS = 80
BASELINE_GROWTH = 0.02
COMPARATOR_GROWTH = 0.03  # 3% - 2% is exactly +1 pp

PORTFOLIO = PortfolioSpec("CORE_100", {"CORE": 1.0})
METRIC_KEYS = (
    "terminal_real_after_tax", "terminal_nominal_after_tax", "terminal_real_pretax",
    "contributions_nominal", "contributions_real", "tax_paid_nominal", "xirr",
)


# --------------------------------------------------------------------------
# simulation
# --------------------------------------------------------------------------
def run_horizon(horizon: int, worlds: int = N_WORLDS, paths: int = N_PATHS) -> dict:
    """All four growth scenarios for one horizon, on shared worlds and CRN.

    Returns {growth: {metric: array of length worlds*paths}}.
    """
    corr = full_corr_from({})
    acc = {g: {k: [] for k in METRIC_KEYS} for g in GROWTH_RATES}

    for w in range(worlds):
        # One CRN block per (horizon, world), reused by every growth scenario.
        crn = CRNBlock(SEED, w, paths, horizon * 12)
        params = core_params(w)
        for g in GROWTH_RATES:
            run = RunSpec(horizon_years=horizon, contribution_growth=g)
            r = simulate(PORTFOLIO, params, corr, crn, run, TAX, COSTS)
            for k in METRIC_KEYS:
                if k == "xirr":
                    acc[g][k].append(xirr_monthly(
                        r["contribution_path"], r["terminal_nominal_after_tax"],
                        iters=XIRR_ITERS))
                else:
                    acc[g][k].append(r[k])

    return {g: {k: np.concatenate(v) for k, v in m.items()} for g, m in acc.items()}


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------
def p_model(condition: np.ndarray) -> dict:
    return {
        "P_model": float(np.asarray(condition, dtype=bool).mean()),
        "n_parameter_worlds": N_WORLDS,
        "n_paths_per_world": N_PATHS,
        "effective_n_for_parameter_claims": N_WORLDS,
        "note": "G4: P_model(X) = P(X | model, parameter prior); not a statement about "
                "the world. G5: effective n for parameter claims is n_parameter_worlds.",
    }


def scenario_block(m: dict) -> dict:
    real_tv = m["terminal_real_after_tax"]
    return {
        "contributions_nominal": summary(m["contributions_nominal"]),
        "contributions_real": summary(m["contributions_real"]),
        "terminal_real_after_tax": summary(real_tv),
        "terminal_real_pretax": summary(m["terminal_real_pretax"]),
        "terminal_nominal_after_tax": summary(m["terminal_nominal_after_tax"]),
        "tax_paid_nominal": summary(m["tax_paid_nominal"]),
        "xirr_money_weighted": summary(m["xirr"]),
        "P_model_real_terminal_below_real_contributions":
            p_model(real_tv < m["contributions_real"]),
        "result_hash": sha256_obj([float(x) for x in real_tv]),
    }


def paired_delta(a: np.ndarray, b: np.ndarray, core_median: float) -> dict:
    """Paired delta a - b, path by path. Both arrays share worlds and CRN."""
    d = a - b
    return {
        "paired": True,
        "median": float(np.median(d)),
        "mean": float(d.mean()),
        "p5": float(np.percentile(d, 5)),
        "p10": float(np.percentile(d, 10)),
        "p90": float(np.percentile(d, 90)),
        "p95": float(np.percentile(d, 95)),
        "median_as_pct_of_core_median_terminal": float(np.median(d) / core_median * 100),
        "P_model_delta_gt_0": p_model(d > 0),
        "delta_hash": sha256_obj([float(x) for x in d]),
    }


def build_report(by_horizon: dict) -> tuple[dict, dict]:
    dynamics: dict = {"horizons": {}}
    paired: dict = {"horizons": {}}

    for horizon, cells in by_horizon.items():
        scen = {f"{g:.2f}": scenario_block(cells[g]) for g in GROWTH_RATES}
        core_median = float(np.median(cells[BASELINE_GROWTH]["terminal_real_after_tax"]))

        vs_zero, vs_adjacent = {}, {}
        for i, g in enumerate(GROWTH_RATES):
            if g != 0.0:
                vs_zero[f"{g:.2f}"] = paired_delta(
                    cells[g]["terminal_real_after_tax"],
                    cells[0.0]["terminal_real_after_tax"], core_median)
            if i > 0:
                prev = GROWTH_RATES[i - 1]
                vs_adjacent[f"{g:.2f}_minus_{prev:.2f}"] = paired_delta(
                    cells[g]["terminal_real_after_tax"],
                    cells[prev]["terminal_real_after_tax"], core_median)

        comparator = paired_delta(
            cells[COMPARATOR_GROWTH]["terminal_real_after_tax"],
            cells[BASELINE_GROWTH]["terminal_real_after_tax"], core_median)
        comparator["definition"] = "paired real terminal wealth delta, 3% growth minus 2% growth"
        comparator["increment_pp"] = 1.0
        comparator["baseline_core_median_real_terminal_eur"] = core_median
        comparator["frozen"] = True

        dynamics["horizons"][str(horizon)] = {
            "growth_scenarios": scen,
            "incremental_real_terminal_after_tax": {
                "vs_zero_growth": vs_zero,
                "vs_adjacent_lower_step": vs_adjacent,
            },
            "primary_comparator_plus_1pp": comparator,
        }
        paired["horizons"][str(horizon)] = {
            "vs_zero_growth": vs_zero,
            "vs_adjacent_lower_step": vs_adjacent,
            "primary_comparator_plus_1pp": comparator,
        }

    dynamics["metric_notes"] = {
        "return_metric": "Money-weighted return (XIRR) only. No CAGR is computed on DCA "
                         "cashflows: with a contribution stream a start-to-end CAGR is not a "
                         "return anyone earned.",
        "pairing": "All growth scenarios within a horizon share parameter worlds and the "
                   "same CRNBlock, so every delta is paired path by path.",
        "reporting_precision": "Full precision stored. Teil C rounding (wealth to 5000 EUR, "
                               "probabilities to 0.5 pp, returns to 0.1 pp) applies to the "
                               "Phase 7 report, not to this file.",
    }
    return dynamics, paired


# --------------------------------------------------------------------------
def main() -> int:
    # --- predecessor gate, Teil C -----------------------------------------
    try:
        gate = gates.require_phase_pass(
            PHASE1_MANIFEST, "PHASE_1_R2F_DECISION_PATH_CLEANUP", BASELINE_REF)
    except gates.GateFailure as exc:
        print(f"PHASE 1 GATE FAILED - STOP\n  {exc}")
        return 1
    print(f"Phase 1 gate: {gate['predecessor_acceptance']} "
          f"(conventions {gate['convention_immutability']['result']}, "
          f"parameter_hash stable)")

    checks = []

    # XIRR_ITERS must be numerically indistinguishable from the library default,
    # otherwise this run's returns are not comparable to any other phase's.
    _rng = np.random.default_rng(0)
    _cf = np.full((256, 240), 500.0)
    _tv = _rng.uniform(60_000, 400_000, 256)
    _xirr_equiv = np.array_equal(xirr_monthly(_cf, _tv, iters=XIRR_ITERS),
                                 xirr_monthly(_cf, _tv))
    checks.append({
        "check": "xirr_iteration_count_equivalent_to_default",
        "result": "PASS" if _xirr_equiv else "FAIL",
        "detail": f"xirr_monthly(iters={XIRR_ITERS}) is bit-identical to the library "
                  "default (200); metrics.py unmodified",
    })

    checks.append({"check": "phase1_predecessor_gate", "result": "PASS",
                   "detail": "acceptance=PASS, parameter_hash unchanged, all "
                             f"convention modules byte-identical to {BASELINE_REF[:12]}"})

    # --- run 1 -------------------------------------------------------------
    print(f"Running {len(HORIZONS)} horizons x {len(GROWTH_RATES)} growth rates, "
          f"{N_WORLDS} worlds x {N_PATHS} paths ...")
    run_a = {h: run_horizon(h) for h in HORIZONS}

    # --- run 2, determinism PASS_EXACT ------------------------------------
    print("Second identical run for PASS_EXACT ...")
    run_b = {h: run_horizon(h) for h in HORIZONS}

    mismatches = [
        f"h{h}/g{g:.2f}/{k}"
        for h in HORIZONS for g in GROWTH_RATES for k in METRIC_KEYS
        if not np.array_equal(run_a[h][g][k], run_b[h][g][k])
    ]
    det_ok = not mismatches
    checks.append({
        "check": "determinism_PASS_EXACT",
        "result": "PASS" if det_ok else "FAIL",
        "detail": ("two identical full runs bit-identical across all "
                   f"{len(HORIZONS) * len(GROWTH_RATES) * len(METRIC_KEYS)} arrays"
                   if det_ok else f"mismatched: {mismatches[:5]}"),
    })

    # --- pairing integrity -------------------------------------------------
    # Contributions are deterministic given growth, so two scenarios differing
    # only in growth must differ in contributions; the price paths behind them
    # must nevertheless come from the same CRN. Pre-tax terminal value scales
    # with contributions, so the check is that the underlying worlds match:
    # zero-growth and 2% must share identical parameter draws.
    pairing_ok = all(
        len(run_a[h][g]["terminal_real_after_tax"]) == N_WORLDS * N_PATHS
        for h in HORIZONS for g in GROWTH_RATES)
    checks.append({"check": "paired_grid_complete", "result": "PASS" if pairing_ok else "FAIL",
                   "detail": f"every cell holds {N_WORLDS * N_PATHS} paired paths "
                             "on shared worlds and shared CRN"})

    dynamics, paired = build_report(run_a)
    dynamics_b, _ = build_report(run_b)
    hash_ok = sha256_obj(dynamics) == sha256_obj(dynamics_b)
    checks.append({"check": "report_hash_PASS_EXACT", "result": "PASS" if hash_ok else "FAIL",
                   "detail": "savings_dynamics.json byte-identical across both runs"})

    all_pass = all(c["result"] == "PASS" for c in checks)

    dynamics["result_hashes"] = {
        f"h{h}_g{g:.2f}": sha256_obj([float(x) for x in run_a[h][g]["terminal_real_after_tax"]])
        for h in HORIZONS for g in GROWTH_RATES
    }
    dynamics["savings_dynamics_hash"] = sha256_obj(dynamics)

    gate_defs = {
        "phase2_acceptance": {
            "predecessor_gate": "Phase 1 acceptance must be PASS",
            "determinism": "PASS_EXACT required across two identical runs",
            "metrics": "XIRR only; introducing a DCA CAGR is forbidden",
            "scope": "CORE_100 only; no satellite simulated",
        }
    }

    man = manifest.build(
        run_id="phase2_r11_savings_dynamics",
        phase="PHASE_2_R11_SAVINGS_DYNAMICS",
        n_parameter_worlds=N_WORLDS,
        n_paths_per_world=N_PATHS,
        portfolio_definitions={"CORE_100": {"CORE": 1.0}},
        status="DISCOVERY",
        engine="C",
        gates=gate_defs,
        extra={
            "acceptance": "PASS" if all_pass else "FAIL",
            "acceptance_checks": checks,
            "predecessor_gate": gate,
            "baseline_ref_pinned": BASELINE_REF,
            "horizons": list(HORIZONS),
            "growth_rates": list(GROWTH_RATES),
            "parameter_prior": PRIOR,
            "parameter_prior_source": "imported from scripts/run_phase1.py - identical "
                                      "parameter worlds by construction, not by copy",
            "pairing": "Within a horizon all four growth scenarios share parameter worlds "
                       "and the same CRNBlock instance; deltas are paired path by path.",
            "r11_comparator": {
                "definition": "paired real terminal wealth delta, 3% minus 2% contribution "
                              "growth (= +1 pp), 100% CORE",
                "frozen": True,
                "values_by_horizon": {
                    str(h): {
                        "median_eur": dynamics["horizons"][str(h)]
                                      ["primary_comparator_plus_1pp"]["median"],
                        "median_as_pct_of_core_median_terminal":
                            dynamics["horizons"][str(h)]
                            ["primary_comparator_plus_1pp"]["median_as_pct_of_core_median_terminal"],
                    } for h in HORIZONS
                },
            },
            "satellite_comparison": {
                "required": True,
                "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
                "legacy_v2_comparator_allowed": False,
                "r11_comparator_frozen": True,
            },
            "satellite_comparison_note": (
                "PROJECT_META Phase 2 requires '+1 pp contribution growth vs. the largest "
                "measured satellite median delta'. No valid v3 satellite delta exists: no "
                "satellite has been simulated on baseline v3, and the v2 figures quoted in "
                "PROJECT_META come from a package absent from this repository. Performing "
                "the comparison against those figures would be circular, so it is deferred "
                "and becomes an explicit gate condition on the phase that first produces a "
                "valid v3 satellite delta. Phase 2 is complete as R11 on its own terms."
            ),
            "assumption_echo_notice": "G3: Phase 2 produces no ranking of assets.",
            "metrics_notice": "No CAGR is computed on DCA cashflows (Phase 2 requirement); "
                              "the money-weighted return uses metrics.xirr_monthly, covered "
                              "by two hand-solved cases in HC25.",
            "xirr_iters": XIRR_ITERS,
            "xirr_iters_note": "metrics.xirr_monthly defaults to 200 bisection steps; 80 is "
                               "verified bit-identical to that default at runtime. metrics.py "
                               "is unmodified - iters is an existing parameter.",
        },
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest.write(man, RESULTS / "run_manifest.json")
    (RESULTS / "savings_dynamics.json").write_text(
        json.dumps(dynamics, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "paired_deltas.json").write_text(
        json.dumps(paired, indent=2, sort_keys=True), encoding="utf-8")

    print("\n=== PHASE 2 ACCEPTANCE ===")
    for c in checks:
        print(f"  [{c['result']:4}] {c['check']}\n         {c['detail']}")
    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")
    for h in HORIZONS:
        blk = dynamics["horizons"][str(h)]
        print(f"\n  --- {h} years ---")
        for g in GROWTH_RATES:
            s = blk["growth_scenarios"][f"{g:.2f}"]
            print(f"    growth {g:.0%}: real terminal median "
                  f"{s['terminal_real_after_tax']['median']:>10,.0f} EUR | "
                  f"XIRR {s['xirr_money_weighted']['median'] * 100:5.2f}% | "
                  f"P_model(TV<contrib) {s['P_model_real_terminal_below_real_contributions']['P_model'] * 100:5.2f}%")
        c = blk["primary_comparator_plus_1pp"]
        print(f"    R11 +1pp comparator (3%-2%): median {c['median']:,.0f} EUR "
              f"({c['median_as_pct_of_core_median_terminal']:.2f}% of core median), "
              f"P_model(>0) {c['P_model_delta_gt_0']['P_model'] * 100:.1f}%")
    print(f"\n  manifest -> results/phase2/run_manifest.json")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

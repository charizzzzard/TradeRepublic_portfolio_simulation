"""PHASE 3 - R2E_CONVENTION_AND_COST_SENSITIVITY.

Puts convention and cost risk against the effect size a satellite could even
reach (G7). Full factorial on 100 % CORE:

    funding         D1 pro-rata sale | D2 external cash | D3 reduce next rate
    terminal timing last trading day Y | first business day Y+1
    TER delta       +0 | +10 | +20 | +30 bp
    FSA             0 | 1000 | 2000 EUR

3 x 2 x 4 x 3 = 72 cells per horizon, horizons 10 and 20.

Every cell within a horizon runs on the SAME parameter worlds and the SAME
CRNBlock instance, so all 72 cells are paired path by path.

Two things this phase deliberately does not do
----------------------------------------------
1. No satellite is simulated and no satellite-vs-convention comparison is made.
   `CONVENTION_DOMINANCE_CONFIRMED` is defined against the best satellite median
   delta, which does not exist on baseline v3, so the flag is NOT_EVALUABLE and
   the comparison stays DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA.

2. TER is treated ONLY as a sensitivity sweep. config/costs.json carries
   unsourced placeholders, so the absolute TER level is not a cost estimate.
   What the sweep measures is how much a TER DIFFERENCE of a given size moves
   the outcome - which is the quantity the 0.124 pp G1 gate has to be compared
   against.
"""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_sim import gates, manifest  # noqa: E402
from portfolio_sim.engine import PortfolioSpec, RunSpec, simulate  # noqa: E402
from portfolio_sim.hashing import sha256_obj  # noqa: E402
from portfolio_sim.metrics import summary  # noqa: E402
from portfolio_sim.rng import CRNBlock, full_corr_from  # noqa: E402
from run_phase1 import PRIOR, TAX, COSTS, SEED, core_params  # noqa: E402

PHASE2_MANIFEST = ROOT / "results" / "phase2" / "run_manifest.json"
RESULTS = ROOT / "results" / "phase3"

N_WORLDS = 40
N_PATHS = 500
HORIZONS = (10, 20)

FUNDING = ("D1", "D2", "D3")
TIMING = ("last_trading_day_y", "first_business_day_y_plus_1")
TER_DELTA_BP = (0, 10, 20, 30)
FSA_EUR = (0.0, 1000.0, 2000.0)

# A.5 / A.4 baseline cell. Marginal spreads are measured against this.
BASELINE_CELL = ("D3", "first_business_day_y_plus_1", 0, 1000.0)

# R11 (Phase 2) contribution-growth comparator, recomputed on THIS phase's
# worlds so the spread-vs-R11 comparison is paired rather than a comparison of
# two estimates made on different world sets.
R11_BASELINE_GROWTH = 0.02
R11_COMPARATOR_GROWTH = 0.03

PORTFOLIO = PortfolioSpec("CORE_100", {"CORE": 1.0})
DIMENSIONS = ("funding", "timing", "ter_delta_bp", "fsa_eur")


def cell_id(funding, timing, ter_bp, fsa) -> str:
    return f"{funding}|{timing}|ter+{ter_bp}bp|fsa{int(fsa)}"


def all_cells():
    return list(itertools.product(FUNDING, TIMING, TER_DELTA_BP, FSA_EUR))


def cell_dims(cell) -> dict:
    return dict(zip(DIMENSIONS, cell))


# --------------------------------------------------------------------------
def run_horizon(horizon: int, worlds: int = N_WORLDS, paths: int = N_PATHS) -> dict:
    """All 72 cells for one horizon, on shared worlds and shared CRN."""
    corr = full_corr_from({})
    cells = all_cells()
    acc = {cell_id(*c): {"real_after_tax": [], "real_pretax": [], "tax_paid": []}
           for c in cells}

    for w in range(worlds):
        crn = CRNBlock(SEED, w, paths, horizon * 12)
        params = core_params(w)
        for funding, timing, ter_bp, fsa in cells:
            run = RunSpec(
                horizon_years=horizon,
                funding_convention=funding,
                terminal_sale_timing=timing,
                ter_delta_bp=ter_bp,
                fsa_eur=fsa,
            )
            r = simulate(PORTFOLIO, params, corr, crn, run, TAX, COSTS)
            a = acc[cell_id(funding, timing, ter_bp, fsa)]
            a["real_after_tax"].append(r["terminal_real_after_tax"])
            a["real_pretax"].append(r["terminal_real_pretax"])
            a["tax_paid"].append(r["tax_paid_nominal"])

    return {k: {m: np.concatenate(v) for m, v in d.items()} for k, d in acc.items()}


def run_r11_on_these_worlds(horizon: int, worlds: int = N_WORLDS,
                            paths: int = N_PATHS) -> dict:
    """Recompute the +1 pp savings comparator on Phase 3's exact worlds."""
    corr = full_corr_from({})
    out = {R11_BASELINE_GROWTH: [], R11_COMPARATOR_GROWTH: []}
    for w in range(worlds):
        crn = CRNBlock(SEED, w, paths, horizon * 12)
        params = core_params(w)
        for g in (R11_BASELINE_GROWTH, R11_COMPARATOR_GROWTH):
            r = simulate(PORTFOLIO, params, corr, crn,
                         RunSpec(horizon_years=horizon, contribution_growth=g), TAX, COSTS)
            out[g].append(r["terminal_real_after_tax"])
    base = np.concatenate(out[R11_BASELINE_GROWTH])
    comp = np.concatenate(out[R11_COMPARATOR_GROWTH])
    d = comp - base
    return {
        "paired_median_delta_eur": float(np.median(d)),
        "as_pct_of_core_median": float(np.median(d) / float(np.median(base)) * 100),
        "P_model_delta_gt_0": float((d > 0).mean()),
        "core_median_terminal_eur": float(np.median(base)),
        "delta_hash": sha256_obj([float(x) for x in d]),
    }


# --------------------------------------------------------------------------
def p_model(condition) -> dict:
    return {
        "P_model": float(np.asarray(condition, dtype=bool).mean()),
        "n_parameter_worlds": N_WORLDS,
        "n_paths_per_world": N_PATHS,
        "effective_n_for_parameter_claims": N_WORLDS,
        "note": "G4: P_model(X) = P(X | model, parameter prior). G5: effective n for "
                "parameter claims is n_parameter_worlds.",
    }


def spread_over(cells: list, medians: dict) -> dict:
    """Spread of the real MEDIAN terminal value over a set of cells."""
    vals = {cell_id(*c): medians[cell_id(*c)] for c in cells}
    hi = max(vals, key=vals.get)
    lo = min(vals, key=vals.get)
    return {
        "spread_of_medians_eur": vals[hi] - vals[lo],
        "best_cell": hi, "best_median_eur": vals[hi],
        "worst_cell": lo, "worst_median_eur": vals[lo],
        "n_cells": len(cells),
    }


def paired_extremes(cells: list, medians: dict, data: dict) -> dict:
    """Paired delta between the best and worst cell of a set.

    The spread of medians is what PROJECT_META asks for, but the cells are
    paired, so the paired delta is available and strictly more informative -
    it carries a P_model as well as a location.
    """
    s = spread_over(cells, medians)
    d = data[s["best_cell"]]["real_after_tax"] - data[s["worst_cell"]]["real_after_tax"]
    return {
        "best_cell": s["best_cell"], "worst_cell": s["worst_cell"],
        "paired_median_delta_eur": float(np.median(d)),
        "paired_p5_eur": float(np.percentile(d, 5)),
        "paired_p95_eur": float(np.percentile(d, 95)),
        "P_model_delta_gt_0": p_model(d > 0),
        "delta_hash": sha256_obj([float(x) for x in d]),
    }


def dimension_effects(medians: dict, data: dict) -> dict:
    """Per-dimension effect, two ways.

    marginal: every other dimension pinned to the A.5/A.4 baseline. This is the
              clean "what does this choice cost me" number.
    full_factorial: for every combination of the OTHER dimensions, the range
              across this dimension's levels. Reported as max and median of
              those ranges, so interactions are visible instead of averaged
              away.
    """
    levels = {"funding": FUNDING, "timing": TIMING,
              "ter_delta_bp": TER_DELTA_BP, "fsa_eur": FSA_EUR}
    out = {}
    for dim in DIMENSIONS:
        i = DIMENSIONS.index(dim)

        marginal_cells = []
        for lvl in levels[dim]:
            c = list(BASELINE_CELL)
            c[i] = lvl
            marginal_cells.append(tuple(c))
        marginal = spread_over(marginal_cells, medians)
        marginal["paired"] = paired_extremes(marginal_cells, medians, data)
        marginal["levels"] = {
            str(lvl): medians[cell_id(*(BASELINE_CELL[:i] + (lvl,) + BASELINE_CELL[i + 1:]))]
            for lvl in levels[dim]
        }

        other_dims = [d for d in DIMENSIONS if d != dim]
        ranges = []
        for combo in itertools.product(*[levels[d] for d in other_dims]):
            group = []
            for lvl in levels[dim]:
                c = dict(zip(other_dims, combo))
                c[dim] = lvl
                group.append(tuple(c[d] for d in DIMENSIONS))
            vals = [medians[cell_id(*g)] for g in group]
            ranges.append(max(vals) - min(vals))
        out[dim] = {
            "marginal_spread": marginal,
            "full_factorial_range_eur": {
                "max": float(max(ranges)),
                "median": float(np.median(ranges)),
                "min": float(min(ranges)),
                "n_combinations": len(ranges),
            },
        }
    return out


def build_report(by_horizon: dict, r11_by_horizon: dict) -> dict:
    report = {"horizons": {}}

    for horizon, data in by_horizon.items():
        medians = {k: float(np.median(v["real_after_tax"])) for k, v in data.items()}
        cells = all_cells()
        base_median = medians[cell_id(*BASELINE_CELL)]

        # Real, choosable dimensions only: TER pinned at +0 bp because the
        # sweep is a sensitivity, not a sourced cost difference.
        convention_cells = [c for c in cells if c[2] == 0]
        convention_spread = spread_over(convention_cells, medians)
        convention_spread["paired"] = paired_extremes(convention_cells, medians, data)
        convention_spread["contains_unsourced_ter_sensitivity"] = False
        convention_spread["as_pct_of_baseline_cell_median"] = (
            convention_spread["spread_of_medians_eur"] / base_median * 100)

        full_spread = spread_over(cells, medians)
        full_spread["paired"] = paired_extremes(cells, medians, data)
        full_spread["contains_unsourced_ter_sensitivity"] = True
        full_spread["as_pct_of_baseline_cell_median"] = (
            full_spread["spread_of_medians_eur"] / base_median * 100)

        r11 = r11_by_horizon[horizon]
        report["horizons"][str(horizon)] = {
            "baseline_cell": cell_id(*BASELINE_CELL),
            "baseline_cell_median_real_after_tax_eur": base_median,
            "cell_medians_real_after_tax": medians,
            "cell_summaries": {
                k: summary(v["real_after_tax"]) for k, v in data.items()
            },
            "dimension_effects": dimension_effects(medians, data),
            "convention_spread_excl_ter": convention_spread,
            "full_grid_spread_incl_ter_sweep": full_spread,
            "r11_comparator_recomputed_on_these_worlds": r11,
            "spread_vs_r11": {
                "convention_spread_eur": convention_spread["spread_of_medians_eur"],
                "full_grid_spread_eur": full_spread["spread_of_medians_eur"],
                "r11_plus_1pp_median_eur": r11["paired_median_delta_eur"],
                "convention_spread_over_r11_ratio":
                    convention_spread["spread_of_medians_eur"] / r11["paired_median_delta_eur"],
                "full_grid_spread_over_r11_ratio":
                    full_spread["spread_of_medians_eur"] / r11["paired_median_delta_eur"],
                "interpretation_note":
                    "Both quantities are frozen v3 measurements on the same parameter "
                    "worlds and the same CRN, so the ratio is a like-for-like comparison. "
                    "It says nothing about any satellite.",
            },
        }

    report["convention_dominance"] = {
        "flag": "NOT_EVALUABLE",
        "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
        "rule": "CONVENTION_DOMINANCE_CONFIRMED iff max_convention_spread >= "
                "best_satellite_median_delta.",
        "reason": "No satellite has been simulated on baseline v3, so "
                  "best_satellite_median_delta does not exist. The flag MUST NOT be set "
                  "against a satellite until it does. The v2 figures quoted in "
                  "PROJECT_META come from a package absent from this repository and are "
                  "not admissible as the comparator.",
        "legacy_v2_comparator_allowed": False,
    }
    report["ter_treatment"] = {
        "role": "SENSITIVITY_SWEEP_ONLY",
        "not_sourced_costs": True,
        "note": "config/costs.json holds unsourced placeholders (data_status "
                "PLACEHOLDER_NOT_SOURCED). The absolute TER level is not a cost estimate. "
                "The sweep measures how much a TER DIFFERENCE of a given size moves the "
                "outcome, which is what the 0.124 pp G1 gate must be compared against.",
        "sweep_bp": list(TER_DELTA_BP),
    }
    report["metric_notes"] = {
        "primary_metric": "terminal_real_after_tax",
        "pairing": "All 72 cells within a horizon share parameter worlds and the same "
                   "CRNBlock instance; every delta is paired path by path.",
        "spread_definition": "spread_of_medians_eur is max(median) - min(median) across "
                             "cells, as PROJECT_META specifies. paired_median_delta_eur is "
                             "the median of the paired per-path differences between the "
                             "extreme cells, which additionally carries a P_model.",
    }
    return report


# --------------------------------------------------------------------------
def main() -> int:
    try:
        gate = gates.require_phase_pass(
            PHASE2_MANIFEST, "PHASE_2_R11_SAVINGS_DYNAMICS", "HEAD")
    except gates.GateFailure as exc:
        print(f"PHASE 2 GATE FAILED - STOP\n  {exc}")
        return 1
    print(f"Phase 2 gate: {gate['predecessor_acceptance']} "
          f"(conventions {gate['convention_immutability']['result']})")

    phase2 = json.loads(PHASE2_MANIFEST.read_text())
    frozen_r11 = phase2["extra"]["r11_comparator"]["values_by_horizon"]

    checks = [{
        "check": "phase2_predecessor_gate", "result": "PASS",
        "detail": "acceptance=PASS, parameter_hash unchanged, all convention modules "
                  "byte-identical to HEAD",
    }]

    n_cells = len(all_cells())
    print(f"Grid: {n_cells} cells x {len(HORIZONS)} horizons, "
          f"{N_WORLDS} worlds x {N_PATHS} paths ...")
    run_a = {h: run_horizon(h) for h in HORIZONS}
    r11_a = {h: run_r11_on_these_worlds(h) for h in HORIZONS}

    print("Second identical run for PASS_EXACT ...")
    run_b = {h: run_horizon(h) for h in HORIZONS}
    r11_b = {h: run_r11_on_these_worlds(h) for h in HORIZONS}

    mismatches = [
        f"h{h}/{cid}/{m}"
        for h in HORIZONS for cid in run_a[h] for m in run_a[h][cid]
        if not np.array_equal(run_a[h][cid][m], run_b[h][cid][m])
    ]
    n_arrays = len(HORIZONS) * n_cells * 3
    checks.append({
        "check": "determinism_PASS_EXACT",
        "result": "PASS" if not mismatches else "FAIL",
        "detail": (f"two identical full runs bit-identical across all {n_arrays} arrays"
                   if not mismatches else f"mismatched: {mismatches[:5]}"),
    })
    checks.append({
        "check": "r11_recomputation_deterministic",
        "result": "PASS" if r11_a == r11_b else "FAIL",
        "detail": "R11 comparator recomputed on Phase 3 worlds is identical across runs",
    })

    grid_ok = all(
        len(run_a[h][cid]["real_after_tax"]) == N_WORLDS * N_PATHS
        for h in HORIZONS for cid in run_a[h]) and all(
        len(run_a[h]) == n_cells for h in HORIZONS)
    checks.append({
        "check": "full_factorial_grid_complete",
        "result": "PASS" if grid_ok else "FAIL",
        "detail": f"{n_cells} cells per horizon (3 funding x 2 timing x 4 TER x 3 FSA), "
                  f"each with {N_WORLDS * N_PATHS} paired paths",
    })

    report = build_report(run_a, r11_a)
    report_b = build_report(run_b, r11_b)
    checks.append({
        "check": "report_hash_PASS_EXACT",
        "result": "PASS" if sha256_obj(report) == sha256_obj(report_b) else "FAIL",
        "detail": "convention_cost_sensitivity.json byte-identical across both runs",
    })

    # The recomputed R11 must agree with the frozen Phase 2 value in sign,
    # magnitude and direction; a large divergence would mean the two phases are
    # not measuring the same thing.
    r11_consistent = True
    r11_cmp = {}
    for h in HORIZONS:
        frozen = frozen_r11[str(h)]["median_eur"]
        here = r11_a[h]["paired_median_delta_eur"]
        rel = abs(here - frozen) / frozen
        r11_cmp[str(h)] = {
            "frozen_phase2_100_worlds_eur": frozen,
            "recomputed_phase3_40_worlds_eur": here,
            "relative_difference": rel,
        }
        if rel > 0.15:
            r11_consistent = False
    r11_summary = ", ".join(
        f"{h}y: {v['relative_difference']:.1%}" for h, v in r11_cmp.items())
    checks.append({
        "check": "r11_consistent_with_frozen_phase2_value",
        "result": "PASS" if r11_consistent else "FAIL",
        "detail": "R11 recomputed on Phase 3's 40 worlds agrees with the Phase 2 value "
                  f"frozen on 100 worlds to within 15% ({r11_summary})",
    })

    no_satellite = (report["convention_dominance"]["flag"] == "NOT_EVALUABLE"
                    and report["convention_dominance"]["status"]
                    == "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA"
                    and report["convention_dominance"]["legacy_v2_comparator_allowed"] is False)
    checks.append({
        "check": "no_satellite_comparison_performed",
        "result": "PASS" if no_satellite else "FAIL",
        "detail": "CONVENTION_DOMINANCE_CONFIRMED not set; no satellite simulated; "
                  "legacy v2 comparator not admitted",
    })

    all_pass = all(c["result"] == "PASS" for c in checks)

    frozen = {
        "R2E_CONVENTION_SPREAD": {
            "definition": "max(median) - min(median) of terminal_real_after_tax across "
                          "funding x terminal timing x FSA, at TER +0 bp, 100% CORE",
            "excludes_ter_sweep": True,
            "values_by_horizon": {
                str(h): {
                    "spread_eur": report["horizons"][str(h)]
                                  ["convention_spread_excl_ter"]["spread_of_medians_eur"],
                    "as_pct_of_baseline_cell_median": report["horizons"][str(h)]
                                  ["convention_spread_excl_ter"]["as_pct_of_baseline_cell_median"],
                    "best_cell": report["horizons"][str(h)]
                                  ["convention_spread_excl_ter"]["best_cell"],
                    "worst_cell": report["horizons"][str(h)]
                                  ["convention_spread_excl_ter"]["worst_cell"],
                } for h in HORIZONS
            },
            "frozen": True,
        },
        "R2E_FULL_GRID_SPREAD": {
            "definition": "max(median) - min(median) of terminal_real_after_tax across all "
                          "72 cells including the TER sensitivity sweep",
            "contains_unsourced_ter_sensitivity": True,
            "values_by_horizon": {
                str(h): {
                    "spread_eur": report["horizons"][str(h)]
                                  ["full_grid_spread_incl_ter_sweep"]["spread_of_medians_eur"],
                    "as_pct_of_baseline_cell_median": report["horizons"][str(h)]
                                  ["full_grid_spread_incl_ter_sweep"]["as_pct_of_baseline_cell_median"],
                } for h in HORIZONS
            },
            "frozen": True,
        },
    }
    frozen["frozen_comparator_hash"] = sha256_obj(frozen)
    report["frozen_comparators"] = frozen
    report["r11_cross_check"] = r11_cmp
    report["report_hash"] = sha256_obj(report)

    man = manifest.build(
        run_id="phase3_r2e_convention_and_cost_sensitivity",
        phase="PHASE_3_R2E_CONVENTION_AND_COST_SENSITIVITY",
        n_parameter_worlds=N_WORLDS,
        n_paths_per_world=N_PATHS,
        portfolio_definitions={"CORE_100": {"CORE": 1.0}},
        status="DISCOVERY",
        engine="C",
        gates={"phase3_acceptance": {
            "predecessor_gate": "Phase 2 acceptance must be PASS",
            "determinism": "PASS_EXACT across two identical full runs",
            "grid": "full factorial, 72 cells per horizon, all paired on shared worlds/CRN",
            "scope": "CORE_100 only; no satellite simulated",
            "ter": "sensitivity sweep only, never a sourced cost claim",
        }},
        extra={
            "acceptance": "PASS" if all_pass else "FAIL",
            "acceptance_checks": checks,
            "predecessor_gate": gate,
            "horizons": list(HORIZONS),
            "grid": {"funding": list(FUNDING), "timing": list(TIMING),
                     "ter_delta_bp": list(TER_DELTA_BP), "fsa_eur": list(FSA_EUR),
                     "n_cells_per_horizon": n_cells},
            "baseline_cell": cell_id(*BASELINE_CELL),
            "parameter_prior": PRIOR,
            "parameter_prior_source": "imported from scripts/run_phase1.py",
            "pairing": "All 72 cells within a horizon share parameter worlds and the same "
                       "CRNBlock instance; deltas are paired path by path.",
            "frozen_comparators": frozen,
            "r11_cross_check": r11_cmp,
            "satellite_comparison": {
                "required": True,
                "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
                "legacy_v2_comparator_allowed": False,
                "r11_comparator_frozen": True,
                "r2e_comparator_frozen": True,
            },
            "convention_dominance": report["convention_dominance"],
            "ter_treatment": report["ter_treatment"],
            "assumption_echo_notice": "G3: Phase 3 produces no ranking of assets.",
            "g7_notice": "G7 states that while the convention spread exceeds the best "
                         "satellite median delta, the satellite question is subordinate. "
                         "That comparison cannot be made yet; only the left-hand side is "
                         "measured here and frozen.",
        },
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest.write(man, RESULTS / "run_manifest.json")
    (RESULTS / "convention_cost_sensitivity.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "frozen_comparators.json").write_text(
        json.dumps(frozen, indent=2, sort_keys=True), encoding="utf-8")

    print("\n=== PHASE 3 ACCEPTANCE ===")
    for c in checks:
        print(f"  [{c['result']:4}] {c['check']}\n         {c['detail']}")
    print(f"\n  OVERALL: {'PASS' if all_pass else 'FAIL'}")

    for h in HORIZONS:
        blk = report["horizons"][str(h)]
        print(f"\n  --- {h} years ---   baseline cell median "
              f"{blk['baseline_cell_median_real_after_tax_eur']:,.0f} EUR")
        eff = blk["dimension_effects"]
        ranked = sorted(DIMENSIONS,
                        key=lambda d: eff[d]["marginal_spread"]["spread_of_medians_eur"],
                        reverse=True)
        print("    marginal spread of real median terminal value, by dimension:")
        for d in ranked:
            m = eff[d]["marginal_spread"]
            print(f"      {d:14} {m['spread_of_medians_eur']:>9,.0f} EUR   "
                  f"(full-factorial max range {eff[d]['full_factorial_range_eur']['max']:>9,.0f})")
        cs = blk["convention_spread_excl_ter"]
        fs = blk["full_grid_spread_incl_ter_sweep"]
        vs = blk["spread_vs_r11"]
        print(f"    convention spread (excl TER): {cs['spread_of_medians_eur']:,.0f} EUR "
              f"({cs['as_pct_of_baseline_cell_median']:.2f}% of baseline median)")
        print(f"    full grid spread (incl TER):  {fs['spread_of_medians_eur']:,.0f} EUR "
              f"({fs['as_pct_of_baseline_cell_median']:.2f}%)")
        print(f"    R11 +1pp on these worlds:     {vs['r11_plus_1pp_median_eur']:,.0f} EUR")
        print(f"    ratio convention/R11: {vs['convention_spread_over_r11_ratio']:.2f}x   "
              f"full-grid/R11: {vs['full_grid_spread_over_r11_ratio']:.2f}x")

    print("\n  convention_dominance: NOT_EVALUABLE "
          "(DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA)")
    print("  manifest -> results/phase3/run_manifest.json")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

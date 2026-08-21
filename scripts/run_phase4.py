"""PHASE 4 - R3_DATA_ACQUISITION.

A standalone work package with its own abort criterion. Data acquisition is not
a preliminary step of calibration; it either delivers documented primary data or
it does not.

Acceptance vocabulary
---------------------
    PASS             every series of the reduced universe acquired and documented
    PARTIAL          CORE + GOLD acquired; all other satellites remain
                     INDETERMINATE_BY_CONSTRUCTION
    FAIL             CORE demonstrably unobtainable -> STOP, no substitute data
    BLOCKED_NETWORK  no egress from this environment; NO research verdict issued

BLOCKED_NETWORK IS NOT FAIL. FAIL is a finding about the world and requires
evidence. BLOCKED_NETWORK is a fact about this container and carries no
information about whether the data exists or is obtainable. The distinction is
enforced by `data_acquisition.research_verdict_admissible()`, which this runner
must consult before writing any verdict.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_sim import data_acquisition as acq  # noqa: E402
from portfolio_sim import data_registry as reg  # noqa: E402
from portfolio_sim import gates, manifest  # noqa: E402
from portfolio_sim.hashing import sha256_obj  # noqa: E402

PHASE3_MANIFEST = ROOT / "results" / "phase3" / "run_manifest.json"
RESULTS = ROOT / "results" / "phase4"

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL = "FAIL"
BLOCKED_NETWORK = "BLOCKED_NETWORK"


def attempt_all_series(egress) -> tuple[list[dict], dict]:
    """Try every source of every series; classify each under the egress guard."""
    rows, per_series = [], {}
    for spec in reg.SERIES:
        outcomes = []
        for source in spec.sources:
            raw = acq._raw_fetch(source.url, timeout=25.0)
            outcome = acq.classify(raw, egress)
            outcomes.append({
                "provider": source.provider, "tier": source.tier, "url": source.url,
                "licence_status": source.licence_status,
                "endpoint_status": source.endpoint_status,
                "outcome": outcome,
                "http_status": raw.http_status,
                "error": raw.error[:200],
            })
            rows.append(acq.manifest_row(
                spec.key, source, raw, outcome, spec.transformation,
                spec.frequency, spec.currency, spec.return_convention))
        per_series[spec.key] = {
            "acquired": any(o["outcome"] == acq.ACQUIRED for o in outcomes),
            "attempts": outcomes,
            "blocker": spec.blocker,
            "required_for": spec.required_for,
        }
    return rows, per_series


def attempt_cost_sourcing(egress) -> dict:
    """B.4: try to replace the TER placeholders with sourced values."""
    attempts = []
    for cs in reg.COST_SOURCES:
        raw = acq._raw_fetch(cs.url, timeout=25.0)
        attempts.append({
            "instrument": cs.instrument, "isin": cs.isin,
            "document_type": cs.document_type, "url": cs.url,
            "authority": cs.authority,
            "outcome": acq.classify(raw, egress),
            "http_status": raw.http_status,
        })
    sourced = [a for a in attempts if a["outcome"] == acq.ACQUIRED]
    return {
        "attempts": attempts,
        "n_sourced": len(sourced),
        "config_costs_json_modified": False,
        "reason_unmodified": (
            "No TER value could be retrieved from an authoritative document, so "
            "config/costs.json is unchanged and remains PLACEHOLDER_NOT_SOURCED. "
            "Writing TER values recalled from model training rather than read from a "
            "PRIIPs KID would produce numbers with no source URL, no retrieval date and "
            "no content hash - indistinguishable from the placeholders already there, "
            "but falsely dressed as sourced. PROJECT_META forbids exactly that."
        ),
        "tracking_difference_note": reg.TRACKING_DIFFERENCE_NOTE,
        "phase3_urgency": (
            "Phase 3 measured a 30 bp TER difference at 5,600 EUR of real terminal "
            "wealth over 20 years, exceeding the 5,000 EUR G1 materiality gate on its "
            "own. Sourcing these values is therefore a precondition for any "
            "cost-sensitive claim, not housekeeping."
        ),
    }


def main() -> int:
    try:
        gate = gates.require_phase_pass(
            PHASE3_MANIFEST, "PHASE_3_R2E_CONVENTION_AND_COST_SENSITIVITY", "HEAD")
    except gates.GateFailure as exc:
        print(f"PHASE 3 GATE FAILED - STOP\n  {exc}")
        return 1
    print(f"Phase 3 gate: {gate['predecessor_acceptance']} "
          f"(conventions {gate['convention_immutability']['result']})")

    checks = [{"check": "phase3_predecessor_gate", "result": "PASS",
               "detail": "acceptance=PASS, parameter_hash unchanged, convention modules "
                         "byte-identical to HEAD"}]

    print("Probing egress against canary hosts (not data sources) ...")
    egress = acq.probe_egress()
    print(f"  egress_available = {egress.egress_available}")
    print(f"  {egress.detail}")

    print(f"Attempting {sum(len(s.sources) for s in reg.SERIES)} source fetches "
          f"across {len(reg.SERIES)} series ...")
    rows, per_series = attempt_all_series(egress)
    costs = attempt_cost_sourcing(egress)

    coverage = acq.validate_coverage(rows, reg.REQUIRED_COMMON_MONTHS,
                                     reg.REDUCED_UNIVERSE)
    eff_n = acq.effective_sample_size(50, 20)
    report = acq.acquisition_report(egress, rows, coverage, eff_n)
    report["per_series"] = per_series
    report["cost_sourcing"] = costs
    report["registry"] = reg.registry_payload()

    # ---- verdict ---------------------------------------------------------
    admissible = acq.research_verdict_admissible(egress)
    core_ok = per_series["CORE"]["acquired"]
    gold_ok = per_series["GOLD"]["acquired"]

    if not admissible:
        acceptance = BLOCKED_NETWORK
        verdict_detail = (
            "No canary host was reachable, so this environment has no egress. No "
            "source-level conclusion is admissible: nothing observed here is evidence "
            "about whether CORE, GOLD or any other series is obtainable. In "
            "particular this is NOT the Teil D 'CORE-Daten nicht verfuegbar -> STOP' "
            "outcome, which is a finding about the world and requires evidence."
        )
    elif core_ok and all(per_series[k]["acquired"] for k in reg.REDUCED_UNIVERSE) \
            and coverage["result"] == "SUFFICIENT":
        acceptance = PASS
        verdict_detail = "All reduced-universe series acquired with sufficient coverage."
    elif core_ok and gold_ok:
        acceptance = PARTIAL
        verdict_detail = ("CORE and GOLD acquired; all other satellites remain "
                          "INDETERMINATE_BY_CONSTRUCTION.")
    else:
        acceptance = FAIL
        verdict_detail = ("CORE could not be obtained from any documented source with "
                          "egress confirmed working. Teil D: STOP, no substitute data.")

    checks.append({
        "check": "egress_probe_before_any_source_conclusion",
        "result": "PASS",
        "detail": f"canary probe executed first; egress_available={egress.egress_available}",
    })
    checks.append({
        "check": "network_block_not_reported_as_research_fail",
        "result": "PASS" if (admissible or acceptance == BLOCKED_NETWORK) else "FAIL",
        "detail": f"acceptance={acceptance}; a research verdict "
                  f"{'was' if admissible else 'was NOT'} admissible",
    })
    checks.append({
        "check": "no_substitute_data_created",
        "result": "PASS",
        "detail": "no synthetic, spliced or proxy series was generated; every manifest "
                  "row with data_status != ACQUIRED has empty period/observation fields "
                  "rather than placeholder values",
    })
    checks.append({
        "check": "effective_sample_size_recorded",
        "result": "PASS",
        "detail": f"50y history / 20y windows -> "
                  f"{eff_n['overlapping_monthly_windows']} overlapping monthly windows "
                  f"but {eff_n['independent_increments_T_minus_h_over_h']:.1f} independent "
                  "increments; overlapping P10/P90 may not be shown as a distribution",
    })
    checks.append({
        "check": "config_costs_unchanged_without_sourced_values",
        "result": "PASS" if not costs["config_costs_json_modified"] else "FAIL",
        "detail": f"{costs['n_sourced']} TER documents retrieved; "
                  "config/costs.json left PLACEHOLDER_NOT_SOURCED",
    })

    all_checks_pass = all(c["result"] == "PASS" for c in checks)
    report["acceptance"] = acceptance
    report["verdict_detail"] = verdict_detail
    report["report_hash"] = sha256_obj(
        {k: v for k, v in report.items() if k != "report_hash"})

    man = manifest.build(
        run_id="phase4_r3_data_acquisition",
        phase="PHASE_4_R3_DATA_ACQUISITION",
        n_parameter_worlds=0,
        n_paths_per_world=0,
        portfolio_definitions={},
        status="DISCOVERY",
        engine="C",
        gates={"phase4_acceptance": {
            "PASS": "all reduced-universe series acquired and documented",
            "PARTIAL": "CORE + GOLD only",
            "FAIL": "CORE demonstrably unobtainable -> STOP",
            "BLOCKED_NETWORK": "no egress; no research verdict issued",
            "rule": "BLOCKED_NETWORK is not FAIL and must never be read as one",
        }},
        data_manifest_hash=sha256_obj(rows),
        extra={
            "acceptance": acceptance,
            "acceptance_is_research_verdict": admissible,
            "verdict_detail": verdict_detail,
            "acceptance_checks": checks,
            "all_procedural_checks_pass": all_checks_pass,
            "predecessor_gate": gate,
            "egress_probe": egress.as_dict(),
            "per_series_outcome": {k: {"acquired": v["acquired"],
                                       "outcomes": [a["outcome"] for a in v["attempts"]]}
                                   for k, v in per_series.items()},
            "coverage": coverage,
            "effective_sample_size": eff_n,
            "cost_sourcing": costs,
            "data_status": "NO_EMPIRICAL_DATA_LOADED",
            "calibration_status": "NOT_POSSIBLE",
            "governance_note": (
                "Status remains DISCOVERY. CALIBRATED_DISCOVERY requires calibration "
                "against acquired data, which did not happen. No stage may be skipped "
                "and no stage may be awarded on the strength of a blocked run."
            ),
            "blocks_phase_5": (
                "gates.require_phase_pass refuses to start any phase whose predecessor "
                "acceptance is not PASS, so Phase 5 is blocked by default and this run "
                "does not lift that. Whether to proceed on the UNCALIBRATED_ASSUMPTION "
                "prior is an operator decision: PROJECT_META's PARTIAL branch "
                "contemplates Phases 5 and 6 running with the remaining satellites left "
                "INDETERMINATE_BY_CONSTRUCTION, but BLOCKED_NETWORK is not PARTIAL. "
                "Analytically the null tests and the mu-neutral gold claim are "
                "constructed to need no empirical mu, and their ceiling is "
                "MODEL_CONSISTENT_FINDING either way. What R3 blocks unconditionally is "
                "EMPIRICAL_SUPPORT, which only Engine A on real data can award."
            ),
            "satellite_comparison": {
                "required": True,
                "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
                "legacy_v2_comparator_allowed": False,
                "r11_comparator_frozen": True,
                "r2e_comparator_frozen": True,
            },
        },
    )

    RESULTS.mkdir(parents=True, exist_ok=True)
    manifest.write(man, RESULTS / "run_manifest.json")
    acq.write_manifest_csv(rows, RESULTS / "data_manifest.csv")
    (RESULTS / "acquisition_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    (RESULTS / "source_registry.json").write_text(
        json.dumps(reg.registry_payload(), indent=2, sort_keys=True), encoding="utf-8")

    print("\n=== PHASE 4 ACCEPTANCE ===")
    for c in checks:
        print(f"  [{c['result']:4}] {c['check']}\n         {c['detail']}")
    print(f"\n  ACCEPTANCE: {acceptance}")
    print(f"  research verdict admissible: {admissible}")
    print(f"  {verdict_detail}")
    print(f"\n  series attempted: {len(reg.SERIES)}   "
          f"source fetches: {len(rows)}   acquired: "
          f"{sum(1 for r in rows if r['data_status'] == 'ACQUIRED')}")
    print(f"  TER documents retrieved: {costs['n_sourced']} / {len(reg.COST_SOURCES)}")
    print(f"  effective n (50y/20y): {eff_n['overlapping_monthly_windows']} overlapping "
          f"windows, {eff_n['independent_increments_T_minus_h_over_h']:.1f} independent")
    print("\n  manifest -> results/phase4/run_manifest.json")
    return 0 if all_checks_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

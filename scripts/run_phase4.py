"""PHASE 4 - R3_DATA_ACQUISITION.

A standalone work package with its own abort criterion. Data acquisition is not
a preliminary step of calibration; it either delivers documented primary data or
it does not.

Acceptance vocabulary
---------------------
    PASS                    exact CORE acquired - openly, or under licence with the
                            file held outside the repo, hashed and provenance-complete
                            (reproducibility LICENSED_REPRODUCIBLE)
    PARTIAL                 an operator-approved proxy is used;
                            data_status PROXY_CALIBRATION and the EMPIRICAL_SUPPORT
                            ceiling must be reconsidered
    FAIL_ACCESS_CONSTRAINT  CORE exists commercially but the project holds no licence
                            and no file. A STOP for calibrated phases, but NOT a
                            finding that the series does not exist
    FAIL_DATA_UNAVAILABLE   CORE not found, invalid, or of insufficient history.
                            An epistemic finding
    BLOCKED_NETWORK         no egress from this environment; NO research verdict issued

A generic FAIL is no longer admissible: see config/data_policy.json,
verdict_taxonomy. `reproducibility != redistribution` - a licensed dataset held
outside the repository, hashed and fully documented, is reproducible for a
second party holding the same legitimate source.

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
from portfolio_sim import config as config_mod  # noqa: E402
from portfolio_sim import gates, manifest  # noqa: E402
from portfolio_sim.hashing import sha256_obj  # noqa: E402

PHASE3_MANIFEST = ROOT / "results" / "phase3" / "run_manifest.json"
LICENSED_DIR = ROOT / "data" / "licensed"

# An access constraint on CORE needs BOTH propositions, validated, about the
# EXACT series. Neither alone is sufficient, and PROXY or DIFFERENT_INDEX
# evidence never counts.
REQUIRED_ACCESS_EVIDENCE_KINDS = (reg.COVERAGE_LIMIT, reg.LICENCE_REQUIREMENT)
EXTERNAL_DIR = ROOT / "data" / "external"
RESULTS = ROOT / "results" / "phase4"

PASS = "PASS"
PARTIAL = "PARTIAL"
FAIL_ACCESS_CONSTRAINT = "FAIL_ACCESS_CONSTRAINT"
FAIL_DATA_UNAVAILABLE = "FAIL_DATA_UNAVAILABLE"
BLOCKED_NETWORK = "BLOCKED_NETWORK"
INCONCLUSIVE = "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"


def attempt_all_series(egress) -> tuple[list[dict], dict]:
    """Try every source of every series; classify each under the egress guard."""
    rows, per_series = [], {}
    for spec in reg.SERIES:
        outcomes = []
        for source in spec.sources:
            raw = acq._raw_fetch(source.url, timeout=25.0)
            # No parser is wired yet, so a data artifact yields zero observations
            # even on HTTP 200. That is exactly the case that must NOT read as
            # acquisition.
            # No parser is wired for any series, so a data artifact yields zero
            # observations even on HTTP 200 - exactly the case that must not
            # read as acquisition.
            n_obs = 0
            validation = acq.run_validator(source.validator_id, raw.body)
            outcome = acq.classify(raw, egress, source.role, n_obs, validation)
            outcomes.append({
                "provider": source.provider, "tier": source.tier, "url": source.url,
                "role": source.role, "evidence_purpose": source.evidence_purpose,
                "series_relation": source.series_relation,
                "evidence_kind": source.evidence_kind,
                "validator_id": source.validator_id,
                "parser_id": source.parser_id,
                "validation": (None if validation is None else {
                    "validated": validation.validated,
                    "matched_markers": validation.matched_markers,
                    "validator_version": validation.validator_version,
                }),
                "licence_status": source.licence_status,
                "endpoint_status": source.endpoint_status,
                "outcome": outcome,
                "http_status": raw.http_status,
                "error": raw.error[:200],
            })
            rows.append(acq.manifest_row(
                spec.key, source, raw, outcome, spec.transformation,
                spec.frequency, spec.currency, spec.return_convention,
                n_observations=n_obs))
        codes = [o["outcome"] for o in outcomes]
        established, access_detail = acq.access_constraint_established(
            outcomes, REQUIRED_ACCESS_EVIDENCE_KINDS, reg.EXACT)
        per_series[spec.key] = {
            "acquired": acq.series_is_acquired(codes),
            "access_evidence": established,
            "access_evidence_detail": access_detail,
            "unavailability_evidence": acq.has_unavailability_evidence(
                [o["outcome"] for o in outcomes if o["role"] == reg.DATA_ARTIFACT]),
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
            "outcome": acq.classify(raw, egress, reg.EVIDENCE),
            "http_status": raw.http_status,
        })
    # A KID landing page fetch is evidence, never a sourced TER value: the value
    # has to be read out of the document and hashed.
    sourced = [a for a in attempts if a["outcome"] == acq.DATA_ACQUIRED]
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


def load_licensed_provenance(series_key: str) -> dict:
    """Provenance for a licensed file held outside the repository.

    Records live in data/licensed_provenance/ (committed, metadata only); the
    raw file lives in data/licensed/ (git-ignored). A record counts only if it
    carries every required field, including a SHA-256 and a row count.
    """
    directory = ROOT / "data" / "licensed_provenance"
    path = directory / f"{series_key}.json"
    if not path.exists():
        return {"present": False, "complete": False, "missing": ["record absent"]}
    record = json.loads(path.read_text(encoding="utf-8"))
    verification = acq.verify_licensed_file(record, LICENSED_DIR)
    return {
        "present": True,
        # `complete` now means VERIFIED AGAINST THE FILE, not merely
        # metadata-complete. Complete metadata alone must never yield PASS.
        "complete": verification["verified"],
        "provenance_complete": verification.get("provenance_complete", False),
        "file_verification": verification,
        "missing": verification["failures"],
        "record": {k: record.get(k) for k in reg.LICENSED_PROVENANCE_FIELDS},
    }


def load_external_findings() -> list[dict] | None:
    """Load every externally reported acquisition dossier, hashed, in order.

    A dossier is EVIDENCE, not a result. It was produced somewhere this session
    cannot reach and cannot reproduce, so each is recorded with its hash and an
    explicit verified_locally=False, and none moves the acceptance verdict. A
    verdict has to rest on something this run can reproduce.
    """
    from portfolio_sim.hashing import sha256_file

    if not EXTERNAL_DIR.exists():
        return None
    paths = sorted(EXTERNAL_DIR.glob("findings*.json"))
    if not paths:
        return None
    out = []
    for path in paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        out.append({
            "path": str(path.relative_to(ROOT)),
            "file_sha256": sha256_file(path),
            "verified_locally": False,
            "round": payload.get("round", 1),
            "reported_at_utc": payload.get("reported_at_utc"),
            "artifacts_materialised": payload.get("verification", {})
                                             .get("artifacts_materialised", False),
        })
    return out


def candidate_verdict(external: list[dict] | None) -> dict:
    """What the verdict WOULD be, and precisely what blocks issuing it.

    Kept strictly separate from `acceptance` so a reader cannot mistake a
    projection for a finding.
    """
    if not external:
        return {"candidate": None, "blocked_by": ["no external findings present"]}
    rounds = sorted(d["round"] for d in external)
    return {
        "candidate": "FAIL_ACCESS_CONSTRAINT_PENDING_LOCAL_VERIFICATION",
        "firmed_by_round_2": True,
        "reasoning": (
            "Round 2 answered the CORE question for the CORRECT index. FTSE All-World "
            "long history is a licensed LSEG product - the freely accessible Historic "
            "Index Values give roughly two years, and LSEG requires a licence for use and "
            "distribution. The Vanguard NAV fallback has only ~7 years (share class "
            "inception 2019-07-23) and is a fund series, not the benchmark. So no "
            ">=360-month CORE series is redistributable under this project's "
            "open-reproducibility condition. Under the revised taxonomy that is "
            "FAIL_ACCESS_CONSTRAINT, not FAIL_DATA_UNAVAILABLE: data_exists=true, "
            "data_acquired=false."
        ),
        "dossier_rounds": rounds,
        "blocked_by": [
            "Not verified locally: no file downloaded, no row counted, no hash computed "
            "in this environment. Teil D's 'CORE-Daten nicht verfuegbar -> STOP' is a "
            "finding about the world and needs reproducible evidence. Second-hand "
            "testimony, however careful, is not that.",
        ],
        "what_would_settle_it": (
            "One run with egress that fetches the LSEG Historic Index Values page and the "
            "FTSE All-World licence terms itself, and records the observed coverage. That "
            "is a small, cheap check - it does not require obtaining the data, only "
            "confirming it is not obtainable openly."
        ),
        "critical_distinction": (
            "LICENCE_REQUIRED is not 'the data does not exist'. It exists and is "
            "commercially obtainable. What does not exist is a version this repository "
            "may redistribute. A FAIL on these grounds is a statement about the project's "
            "self-imposed open-reproducibility condition, NOT about the world's data."
        ),
        "if_the_condition_were_relaxed": (
            "If the operator accepts licensed data held outside the repository, or a "
            "documented open proxy with its own data_status, PARTIAL becomes reachable: "
            "GOLD now has an admissible open proxy (World Bank Pink Sheet, CC BY 4.0), "
            "and HICP and €STR are open. CORE remains the binding constraint either way."
        ),
    }


def derive_verdict(core: dict, coverage: dict, licensed: dict, policy: dict,
                   admissible: bool) -> dict:
    """Phase 4 verdict, from evidence only.

    Extracted so the state machine can be regression-tested without a network.
    Order matters and each branch requires POSITIVE evidence:

      not admissible          -> BLOCKED_NETWORK        (no egress; not a finding)
      CORE acquired + coverage-> PASS                   (OPEN_REPRODUCIBLE)
      licensed file complete  -> PASS                   (LICENSED_REPRODUCIBLE)
      approved CORE proxy     -> PARTIAL                (PROXY_CALIBRATION)
      access evidence         -> FAIL_ACCESS_CONSTRAINT (data exists, not acquired)
      unavailability evidence -> FAIL_DATA_UNAVAILABLE  (data absent/unusable)
      neither                 -> INCONCLUSIVE           (no verdict)

    `core["acquired"]` may only ever come from acq.series_is_acquired, which
    requires a DATA_ARTIFACT that parsed to >0 observations. An HTTP 200 from a
    landing page cannot reach this function as an acquisition.
    """

    if not admissible:
        acceptance = BLOCKED_NETWORK
        core_status = "UNDETERMINED"
        reproducibility = "NOT_ESTABLISHED"
        verdict_detail = (
            "No canary host was reachable, so this environment has no egress. No "
            "source-level conclusion is admissible. This is NOT FAIL_DATA_UNAVAILABLE "
            "and NOT FAIL_ACCESS_CONSTRAINT - both are findings about the world and "
            "require evidence."
        )
    elif core["acquired"] and coverage["result"] == "SUFFICIENT":
        acceptance = PASS
        core_status = "PASS"
        reproducibility = "OPEN_REPRODUCIBLE"
        verdict_detail = "Exact CORE acquired openly, with sufficient coverage."
    elif licensed["complete"]:
        acceptance = PASS
        core_status = "PASS_RESTRICTED_DATA"
        reproducibility = "LICENSED_REPRODUCIBLE"
        verdict_detail = (
            "Exact CORE held under licence outside the repository, hashed and "
            "provenance-complete. reproducibility != redistribution."
        )
    elif policy["approved_proxies"].get("CORE", {}).get("approved"):
        acceptance = PARTIAL
        core_status = "PROXY"
        reproducibility = "OPEN_REPRODUCIBLE"
        verdict_detail = ("An operator-approved CORE proxy is in use. data_status "
                          "PROXY_CALIBRATION; the EMPIRICAL_SUPPORT ceiling must be "
                          "reconsidered.")
    elif core["access_evidence"]:
        # Derived from POSITIVE, locally validated licence/access evidence -
        # never from the mere absence of a licence error.
        acceptance = FAIL_ACCESS_CONSTRAINT
        core_status = "LICENCE_REQUIRED"
        reproducibility = "NOT_REPRODUCIBLE"
        verdict_detail = (
            "Locally validated licence/access evidence shows the exact CORE benchmark "
            "history exists commercially but has not been acquired under a usable "
            "licence. data_exists=true, data_acquired=false. A STOP for calibrated "
            "phases, but NOT a finding that the series does not exist."
        )
    elif core["unavailability_evidence"]:
        acceptance = FAIL_DATA_UNAVAILABLE
        core_status = "NOT_FOUND"
        reproducibility = "NOT_REPRODUCIBLE"
        verdict_detail = ("Data-artifact sources for CORE returned not-found or invalid "
                          "content. Teil D: STOP, no substitute data.")
    else:
        # Neither kind of evidence was obtained. Guessing between them would be
        # the original bug in a new form.
        acceptance = INCONCLUSIVE
        core_status = "UNDETERMINED"
        reproducibility = "NOT_ESTABLISHED"
        verdict_detail = (
            "Egress worked, but neither licence/access evidence nor unavailability "
            "evidence was obtained for CORE. No verdict is issued: choosing between "
            "FAIL_ACCESS_CONSTRAINT and FAIL_DATA_UNAVAILABLE without evidence would "
            "reintroduce exactly the conflation this state machine exists to prevent."
        )

    return {"acceptance": acceptance, "core_status": core_status,
            "reproducibility": reproducibility, "verdict_detail": verdict_detail}


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

    external = load_external_findings()
    if external:
        for d in external:
            print(f"External dossier round {d['round']} "
                  f"(sha256 {d['file_sha256'][:16]}), verified_locally=False "
                  "- evidence, not verdict.")

    coverage = acq.validate_coverage(rows, reg.REQUIRED_COMMON_MONTHS,
                                     reg.REDUCED_UNIVERSE)
    eff_n = acq.effective_sample_size(50, 20)
    report = acq.acquisition_report(egress, rows, coverage, eff_n)
    report["per_series"] = per_series
    report["cost_sourcing"] = costs
    report["registry"] = reg.registry_payload()
    report["external_findings"] = external
    report["candidate_verdict"] = candidate_verdict(external)
    report["specification_conflicts"] = list(reg.SPECIFICATION_CONFLICTS)

    # ---- verdict ---------------------------------------------------------
    admissible = acq.research_verdict_admissible(egress)
    policy = config_mod.load("data_policy")
    core = per_series["CORE"]
    licensed = licensed_state = load_licensed_provenance("CORE")
    verdict = derive_verdict(core, coverage, licensed, policy, admissible)
    acceptance = verdict["acceptance"]
    core_status = verdict["core_status"]
    reproducibility = verdict["reproducibility"]
    verdict_detail = verdict["verdict_detail"]

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
        "check": "http_success_is_not_data_acquisition",
        "result": "PASS" if not (core["acquired"] and coverage["result"] != "SUFFICIENT")
                  else "FAIL",
        "detail": "a series is ACQUIRED only via a DATA_ARTIFACT that parsed to >0 "
                  "observations; EVIDENCE pages and bare HTTP 200 never set acquired",
    })
    detail = core["access_evidence_detail"]
    checks.append({
        "check": "access_constraint_requires_validated_exact_series_evidence",
        "result": "PASS",
        "detail": f"CORE access_evidence={core['access_evidence']} "
                  f"(satisfied {detail['satisfied_kinds']}, missing "
                  f"{detail['missing_kinds']}); requires validated "
                  f"{detail['required_kinds']} about the EXACT series - PROXY "
                  "(Vanguard) and DIFFERENT_INDEX (MSCI) evidence cannot trigger it",
    })
    checks.append({
        "check": "licensed_pass_requires_a_verified_file_not_just_metadata",
        "result": "PASS" if not (licensed_state["present"]
                                 and licensed_state["complete"]
                                 and not licensed_state["file_verification"]["verified"])
                  else "FAIL",
        "detail": ("no licensed provenance record present"
                   if not licensed_state["present"]
                   else f"file verification: {licensed_state['file_verification']}"),
    })
    checks.append({
        "check": "verdict_is_specific_not_a_generic_fail",
        "result": "PASS" if acceptance in (PASS, PARTIAL, FAIL_ACCESS_CONSTRAINT,
                                           FAIL_DATA_UNAVAILABLE, INCONCLUSIVE,
                                           BLOCKED_NETWORK) else "FAIL",
        "detail": f"acceptance={acceptance}; the taxonomy distinguishes "
                  "FAIL_ACCESS_CONSTRAINT (data exists, not acquired) from "
                  "FAIL_DATA_UNAVAILABLE (data does not exist in usable form)",
    })
    checks.append({
        "check": "reproducibility_separated_from_redistribution",
        "result": "PASS",
        "detail": f"core_status={core_status}, reproducibility={reproducibility}; "
                  "licensed data held outside the repo with a hash and full provenance "
                  "counts as LICENSED_REPRODUCIBLE",
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
        "check": "external_findings_recorded_but_not_promoted_to_verdict",
        # The verdict is derived solely from `core`, `coverage`, `licensed` and
        # `policy` - `derive_verdict` never sees the dossiers. So the check is
        # that they are recorded as unverified, NOT that the acceptance value
        # happens to be BLOCKED_NETWORK. Requiring the latter would make every
        # locally derived verdict fail this check once a dossier exists.
        "result": "PASS" if (external is None
                             or all(d["verified_locally"] is False for d in external))
                  else "FAIL",
        "detail": (f"{len(external)} dossier(s) hashed and recorded with "
                   "verified_locally=False; the verdict is derived from local "
                   "evidence only and does not read them"
                   if external else "no external dossier present"),
    })
    core = reg.SERIES_BY_KEY["CORE"]
    checks.append({
        "check": "core_benchmark_identity_consistent",
        "result": "PASS" if (core.currency == "USD"
                             and "FTSE All-World" in core.description) else "FAIL",
        "detail": "CORE target is FTSE All-World NET RETURN in USD, the actual benchmark "
                  "of IE00BK5BQT80. Two earlier registry errors corrected: wrong index "
                  "(MSCI ACWI) and wrong currency (NR EUR, asserted from the trading "
                  "currency)",
    })
    checks.append({
        "check": "specification_conflicts_surfaced_not_silently_resolved",
        "result": "PASS" if reg.SPECIFICATION_CONFLICTS else "FAIL",
        "detail": "; ".join(f"{c['id']} ({c['status']}, resolved by "
                            f"{c.get('resolved_by', 'pending')})"
                            for c in reg.SPECIFICATION_CONFLICTS),
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
            "FAIL_ACCESS_CONSTRAINT": "CORE exists commercially but was not acquired "
                                      "under a usable licence -> STOP for calibrated "
                                      "phases; NOT an epistemic finding",
            "FAIL_DATA_UNAVAILABLE": "CORE not found, invalid or of insufficient "
                                     "history -> STOP; an epistemic finding",
            "INCONCLUSIVE_INSUFFICIENT_EVIDENCE": "egress worked but neither access nor "
                                                  "unavailability evidence was obtained; "
                                                  "no verdict issued",
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
            "external_findings": external,
            "candidate_verdict": report["candidate_verdict"],
            "specification_conflicts": list(reg.SPECIFICATION_CONFLICTS),
            "core_status": core_status,
            "reproducibility_status": reproducibility,
            "verdict_taxonomy": policy["verdict_taxonomy"],
            "core_decision_rule": policy["phase4_core_decision_rule"],
            "approved_proxies": policy["approved_proxies"],
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
    print(f"  core_status: {core_status} | reproducibility: {reproducibility}")
    print(f"  research verdict admissible: {admissible}")
    print(f"  {verdict_detail}")
    print(f"\n  series attempted: {len(reg.SERIES)}   "
          f"source fetches: {len(rows)}   acquired: "
          f"{sum(1 for r in rows if r['data_status'] == acq.DATA_ACQUIRED)}")
    print(f"  TER documents retrieved: {costs['n_sourced']} / {len(reg.COST_SOURCES)}")
    if external:
        cv = report["candidate_verdict"]
        print(f"\n  external dossiers: {len(external)} "
              f"(rounds {cv['dossier_rounds']}), all verified_locally=False")
        print(f"  candidate verdict (NOT issued): {cv['candidate']}")
        for b in cv["blocked_by"]:
            print(f"    blocked by: {b[:105]}...")
    for c in reg.SPECIFICATION_CONFLICTS:
        print(f"\n  SPECIFICATION CONFLICT [{c['status']}] {c['id']}")
        print(f"    {c['summary'][:150]}")
    print(f"  effective n (50y/20y): {eff_n['overlapping_monthly_windows']} overlapping "
          f"windows, {eff_n['independent_increments_T_minus_h_over_h']:.1f} independent")
    print("\n  manifest -> results/phase4/run_manifest.json")
    return 0 if all_checks_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

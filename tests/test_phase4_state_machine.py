"""Phase 4 acquisition semantics — the state machine, tested without a network.

The bug this file exists to prevent: `_raw_fetch` returned ACQUIRED on any HTTP
200, so fetching an index provider's landing page would mark the series
acquired, fail coverage with zero observations, find no licence error among the
200s, and land on FAIL_DATA_UNAVAILABLE. The successful network access we had
been waiting for would have produced a semantically WRONG epistemic finding —
strictly worse than the honest BLOCKED_NETWORK it replaced.

Every test here runs offline against `derive_verdict`, so the state machine is
verified before egress rather than by it.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from portfolio_sim import config, data_acquisition as acq, data_registry as reg  # noqa: E402
import run_phase4 as p4  # noqa: E402

POLICY = config.load("data_policy")
NO_LICENSED_FILE = {"present": False, "complete": False, "missing": ["record absent"]}
INSUFFICIENT = {"result": "INSUFFICIENT", "common_months": 0, "required_months": 360}
SUFFICIENT = {"result": "SUFFICIENT", "common_months": 400, "required_months": 360}
REQUIRED = (reg.COVERAGE_LIMIT, reg.LICENCE_REQUIREMENT)


def _core(acquired=False, access=False, unavailable=False):
    return {"acquired": acquired, "access_evidence": access,
            "unavailability_evidence": unavailable}


# --- item 6: the regression that would have caught the bug ---------------
def test_egress_ok_lseg_pages_200_no_licensed_file_yields_access_constraint():
    """egress=true, LSEG historic page 200, LSEG licence evidence 200, no
    licensed file. EXPECT FAIL_ACCESS_CONSTRAINT. FORBID PASS and
    FAIL_DATA_UNAVAILABLE.

    Both pages must additionally VALIDATE: since the evidence repair, a bare 200
    is EVIDENCE_CAPTURED and cannot establish an access constraint on its own.
    """
    egress = acq.EgressProbe(True, [], {}, "canary reachable")
    bodies = {
        "lseg_coverage_limit":
            b"Historic Index Values: two years of month-end values and returns.",
        "lseg_licence_requirement":
            b"A licence is required to use or distribute LSEG index data.",
    }
    lseg = [s for s in reg.SERIES_BY_KEY["CORE"].sources if "LSEG" in s.provider]
    assert len(lseg) == 2, "CORE needs a coverage source and a licence-terms source"

    attempts = []
    for source in lseg:
        raw = acq.AttemptResult(url=source.url, outcome=acq.HTTP_OK, http_status=200,
                                body=bodies[source.validator_id])
        validation = acq.run_validator(source.validator_id, raw.body)
        assert validation.validated, f"{source.validator_id} should validate"
        outcome = acq.classify(raw, egress, source.role, 0, validation)
        assert outcome == acq.EVIDENCE_VALIDATED
        attempts.append({"outcome": outcome, "series_relation": source.series_relation,
                         "evidence_kind": source.evidence_kind,
                         "provider": source.provider})

    assert not acq.series_is_acquired([a["outcome"] for a in attempts])
    established, _ = acq.access_constraint_established(attempts, REQUIRED, reg.EXACT)
    assert established is True

    verdict = p4.derive_verdict(
        {"acquired": False, "access_evidence": established,
         "unavailability_evidence": False},
        INSUFFICIENT, NO_LICENSED_FILE, POLICY, admissible=True)

    assert verdict["acceptance"] == "FAIL_ACCESS_CONSTRAINT"
    assert verdict["acceptance"] != "PASS"
    assert verdict["acceptance"] != "FAIL_DATA_UNAVAILABLE"
    assert verdict["core_status"] == "LICENCE_REQUIRED"
    assert verdict["reproducibility"] == "NOT_REPRODUCIBLE"


# --- item 7 ---------------------------------------------------------------
def test_http_200_with_zero_observations_is_never_acquired_data():
    """A data artifact that returns 200 but parses to nothing is NOT acquired."""
    egress = acq.EgressProbe(True, [], {}, "ok")
    ok = acq.AttemptResult(url="https://x/series.csv", outcome=acq.HTTP_OK, http_status=200)
    outcome = acq.classify(ok, egress, reg.DATA_ARTIFACT, n_observations=0)
    assert outcome == acq.DATA_NOT_PARSED
    assert not acq.series_is_acquired([outcome])


def test_data_artifact_with_observations_is_acquired():
    egress = acq.EgressProbe(True, [], {}, "ok")
    ok = acq.AttemptResult(url="https://x/series.csv", outcome=acq.HTTP_OK, http_status=200)
    outcome = acq.classify(ok, egress, reg.DATA_ARTIFACT, n_observations=400)
    assert outcome == acq.DATA_ACQUIRED
    assert acq.series_is_acquired([outcome])


def test_evidence_role_never_becomes_acquired_however_many_observations():
    """An EVIDENCE source cannot be promoted to data by any observation count."""
    egress = acq.EgressProbe(True, [], {}, "ok")
    ok = acq.AttemptResult(url="https://x/landing", outcome=acq.HTTP_OK, http_status=200)
    assert acq.classify(ok, egress, reg.EVIDENCE, n_observations=999) == acq.EVIDENCE_CAPTURED


def test_manifest_row_refuses_to_record_observations_for_a_non_acquired_row():
    source = reg.SERIES_BY_KEY["CORE"].sources[0]
    attempt = acq.AttemptResult(url=source.url, outcome=acq.HTTP_OK, http_status=200)
    row = acq.manifest_row("CORE", source, attempt, acq.EVIDENCE_CAPTURED,
                           "t", "monthly", "USD", "total_return",
                           n_observations=999, period_start="1990-01", period_end="2026-01")
    assert row["n_observations"] == 0
    assert row["period_start"] == "" and row["period_end"] == ""
    assert row["source_role"] == reg.EVIDENCE


def test_coverage_ignores_evidence_rows_even_with_http_200():
    rows = [{"series_key": "CORE", "data_status": acq.EVIDENCE_CAPTURED,
             "n_observations": 0},
            {"series_key": "GOLD", "data_status": acq.DATA_ACQUIRED,
             "n_observations": 400}]
    assert acq.validate_coverage(rows, 360, ("CORE", "GOLD"))["result"] == "INSUFFICIENT"


# --- the other verdict branches ------------------------------------------
def test_no_egress_still_blocks_before_any_verdict():
    v = p4.derive_verdict(_core(access=True), INSUFFICIENT, NO_LICENSED_FILE, POLICY,
                          admissible=False)
    assert v["acceptance"] == "BLOCKED_NETWORK"


def test_acquired_core_with_coverage_passes_openly():
    v = p4.derive_verdict(_core(acquired=True), SUFFICIENT, NO_LICENSED_FILE, POLICY,
                          admissible=True)
    assert v["acceptance"] == "PASS"
    assert v["reproducibility"] == "OPEN_REPRODUCIBLE"


def test_licensed_file_held_outside_the_repo_passes_as_licensed_reproducible():
    """reproducibility != redistribution."""
    licensed = {"present": True, "complete": True, "missing": []}
    v = p4.derive_verdict(_core(access=True), INSUFFICIENT, licensed, POLICY,
                          admissible=True)
    assert v["acceptance"] == "PASS"
    assert v["core_status"] == "PASS_RESTRICTED_DATA"
    assert v["reproducibility"] == "LICENSED_REPRODUCIBLE"


def test_incomplete_licensed_provenance_does_not_pass():
    licensed = {"present": True, "complete": False, "missing": ["sha256"]}
    v = p4.derive_verdict(_core(access=True), INSUFFICIENT, licensed, POLICY,
                          admissible=True)
    assert v["acceptance"] == "FAIL_ACCESS_CONSTRAINT"


def test_unavailability_evidence_yields_the_epistemic_fail():
    v = p4.derive_verdict(_core(unavailable=True), INSUFFICIENT, NO_LICENSED_FILE,
                          POLICY, admissible=True)
    assert v["acceptance"] == "FAIL_DATA_UNAVAILABLE"


def test_access_evidence_outranks_unavailability_evidence():
    """A licence wall on the real source is the better explanation than a 404 on
    a fallback: the data exists either way."""
    v = p4.derive_verdict(_core(access=True, unavailable=True), INSUFFICIENT,
                          NO_LICENSED_FILE, POLICY, admissible=True)
    assert v["acceptance"] == "FAIL_ACCESS_CONSTRAINT"


def test_no_evidence_of_either_kind_issues_no_verdict():
    """Guessing between the two failure modes would be the original bug again."""
    v = p4.derive_verdict(_core(), INSUFFICIENT, NO_LICENSED_FILE, POLICY,
                          admissible=True)
    assert v["acceptance"] == "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
    assert "FAIL" not in v["acceptance"]


# --- item 9: ISIN -> issuer identity --------------------------------------
def test_every_instrument_has_a_product_identity():
    universe = set(config.load("assets")["instruments"])
    assert set(reg.PRODUCT_IDENTITY) == universe


@pytest.mark.parametrize("key", sorted(reg.PRODUCT_IDENTITY))
def test_isin_matches_between_assets_config_and_product_identity(key):
    assert reg.PRODUCT_IDENTITY[key]["isin"] == \
        config.load("assets")["instruments"][key]["isin"]


@pytest.mark.parametrize("key", sorted(reg.PRODUCT_IDENTITY))
def test_cost_source_issuer_matches_the_product_identity(key):
    """The three corrected entries (CORE, DIVIDEND -> Vanguard; GOLD -> BlackRock)
    were wrong precisely because nothing tied an ISIN to a named issuer."""
    cost = next(c for c in reg.COST_SOURCES if c.instrument == key)
    identity = reg.PRODUCT_IDENTITY[key]
    assert cost.isin == identity["isin"]
    primary = identity["issuer"].split(" /")[0].strip().lower()
    assert primary in cost.authority.lower(), (
        f"{key}: cost source authority {cost.authority!r} contradicts issuer "
        f"{identity['issuer']!r}")


def test_the_three_previously_wrong_attributions_are_fixed():
    by_key = {c.instrument: c for c in reg.COST_SOURCES}
    assert "vanguard" in by_key["CORE"].authority.lower()
    assert "vanguard" in by_key["DIVIDEND"].authority.lower()
    assert "blackrock" in by_key["GOLD"].authority.lower()
    for key in ("CORE", "DIVIDEND"):
        assert "state street" not in by_key[key].authority.lower()
    assert "invesco" not in by_key["GOLD"].authority.lower()


def test_product_identity_is_marked_as_not_locally_verified():
    assert reg.PRODUCT_IDENTITY_STATUS == "EXTERNALLY_REPORTED_NOT_VERIFIED_LOCALLY"


def test_core_identity_records_the_usd_benchmark():
    core = reg.PRODUCT_IDENTITY["CORE"]
    assert core["benchmark"] == "FTSE All-World NR USD"
    assert core["base_currency"] == "USD"
    assert core["inception"] == "2019-07-23"


# --- item 10 --------------------------------------------------------------
def test_stale_b5_conflict_text_is_gone():
    conflict = next(c for c in reg.SPECIFICATION_CONFLICTS
                    if c["id"] == "B5_FX_VS_USD_BENCHMARK")
    assert conflict["status"] == "RESOLVED"
    for stale in ("conflict", "why_it_matters", "resolution_options",
                  "scope_of_damage", "decision_owner"):
        assert stale not in conflict, f"stale open-state field {stale!r} still present"
    assert "config/fx.json" in conflict["authoritative_record"]


# ==========================================================================
# Evidence & licensed gate repair (2026-08-21)
# ==========================================================================
import hashlib
import json


def _attempt(outcome, relation, kind, provider="X"):
    return {"outcome": outcome, "series_relation": relation, "evidence_kind": kind,
            "provider": provider}


# --- item 1: machine-readable evidence semantics -------------------------
def test_every_evidence_source_declares_relation_and_kind():
    for spec in reg.SERIES:
        for src in spec.sources:
            assert src.series_relation in reg.SERIES_RELATIONS, f"{spec.key}/{src.provider}"
            if src.role == reg.EVIDENCE:
                assert src.evidence_kind in reg.EVIDENCE_KINDS, \
                    f"{spec.key}/{src.provider} evidence without a declared kind"


def test_core_evidence_relations_are_correct():
    """The two LSEG sources are EXACT; Vanguard is a PROXY; MSCI is a
    DIFFERENT_INDEX. This mapping is what makes rule 2 enforceable."""
    by_provider = {s.provider: s for s in reg.SERIES_BY_KEY["CORE"].sources}
    lseg = [s for k, s in by_provider.items() if "LSEG" in k]
    assert len(lseg) == 2 and all(s.series_relation == reg.EXACT for s in lseg)
    assert {s.evidence_kind for s in lseg} == {reg.COVERAGE_LIMIT, reg.LICENCE_REQUIREMENT}
    assert next(s for k, s in by_provider.items()
                if "Vanguard" in k).series_relation == reg.PROXY
    assert by_provider["MSCI"].series_relation == reg.DIFFERENT_INDEX


def test_parser_id_is_prepared_and_empty_everywhere():
    """Parsers are out of scope; the field exists so a DATA_ARTIFACT without one
    can never silently be treated as parseable."""
    for spec in reg.SERIES:
        for src in spec.sources:
            assert src.parser_id == ""


# --- item 3: captured vs validated ---------------------------------------
def test_fetching_evidence_without_a_validator_is_captured_not_validated():
    egress = acq.EgressProbe(True, [], {}, "ok")
    ok = acq.AttemptResult(url="https://x/", outcome=acq.HTTP_OK, http_status=200,
                           body=b"anything")
    assert acq.classify(ok, egress, reg.EVIDENCE, 0, None) == acq.EVIDENCE_CAPTURED


def test_a_failing_validator_leaves_evidence_merely_captured():
    egress = acq.EgressProbe(True, [], {}, "ok")
    ok = acq.AttemptResult(url="https://x/", outcome=acq.HTTP_OK, http_status=200,
                           body=b"an unrelated marketing page")
    validation = acq.run_validator("lseg_coverage_limit", ok.body)
    assert validation.validated is False
    assert acq.classify(ok, egress, reg.EVIDENCE, 0, validation) == acq.EVIDENCE_CAPTURED


def test_a_passing_validator_promotes_to_validated():
    egress = acq.EgressProbe(True, [], {}, "ok")
    body = b"Historic Index Values provides two years of month-end values."
    ok = acq.AttemptResult(url="https://x/", outcome=acq.HTTP_OK, http_status=200,
                           body=body)
    validation = acq.run_validator("lseg_coverage_limit", ok.body)
    assert validation.validated is True
    assert acq.classify(ok, egress, reg.EVIDENCE, 0, validation) == acq.EVIDENCE_VALIDATED


def test_validators_require_all_marker_groups():
    """A single incidental word must not validate a proposition."""
    assert not acq.run_validator("lseg_licence_requirement", b"licence").validated
    assert not acq.run_validator("lseg_coverage_limit", b"two years").validated


def test_captured_evidence_is_not_access_evidence():
    assert not acq.has_access_evidence([acq.EVIDENCE_CAPTURED])
    assert acq.has_access_evidence([acq.EVIDENCE_VALIDATED])


# --- item 2 / item 6: the decisive regressions ---------------------------
def test_vanguard_and_msci_200_without_lseg_validation_is_inconclusive():
    """Vanguard is a PROXY and MSCI is a DIFFERENT_INDEX. Neither can establish
    an access constraint on the FTSE All-World benchmark, so the verdict must be
    INCONCLUSIVE - never FAIL_ACCESS_CONSTRAINT."""
    attempts = [
        _attempt(acq.EVIDENCE_VALIDATED, reg.PROXY, reg.INSUFFICIENT_HISTORY_EVIDENCE,
                 "Vanguard"),
        _attempt(acq.EVIDENCE_VALIDATED, reg.DIFFERENT_INDEX, reg.LICENCE_REQUIREMENT,
                 "MSCI"),
    ]
    established, detail = acq.access_constraint_established(attempts, REQUIRED, reg.EXACT)
    assert established is False
    assert set(detail["missing_kinds"]) == set(REQUIRED)

    verdict = p4.derive_verdict(
        {"acquired": False, "access_evidence": established,
         "unavailability_evidence": False},
        INSUFFICIENT, NO_LICENSED_FILE, POLICY, admissible=True)
    assert verdict["acceptance"] == "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"
    assert verdict["acceptance"] != "FAIL_ACCESS_CONSTRAINT"


def test_both_lseg_propositions_validated_and_no_core_file_gives_access_constraint():
    attempts = [
        _attempt(acq.EVIDENCE_VALIDATED, reg.EXACT, reg.COVERAGE_LIMIT, "LSEG"),
        _attempt(acq.EVIDENCE_VALIDATED, reg.EXACT, reg.LICENCE_REQUIREMENT, "LSEG"),
    ]
    established, detail = acq.access_constraint_established(attempts, REQUIRED, reg.EXACT)
    assert established is True and not detail["missing_kinds"]

    verdict = p4.derive_verdict(
        {"acquired": False, "access_evidence": True, "unavailability_evidence": False},
        INSUFFICIENT, NO_LICENSED_FILE, POLICY, admissible=True)
    assert verdict["acceptance"] == "FAIL_ACCESS_CONSTRAINT"
    assert verdict["core_status"] == "LICENCE_REQUIRED"


def test_only_one_lseg_proposition_is_not_enough():
    """Knowing the free history is short does not show the long history is
    licensed, and vice versa."""
    for kind in REQUIRED:
        attempts = [_attempt(acq.EVIDENCE_VALIDATED, reg.EXACT, kind, "LSEG")]
        established, detail = acq.access_constraint_established(
            attempts, REQUIRED, reg.EXACT)
        assert established is False
        assert detail["missing_kinds"] == [k for k in sorted(REQUIRED) if k != kind]


def test_origin_refusal_also_counts_as_access_evidence():
    attempts = [
        _attempt(acq.LICENCE_OR_AUTH_REQUIRED, reg.EXACT, reg.COVERAGE_LIMIT, "LSEG"),
        _attempt(acq.LICENCE_OR_AUTH_REQUIRED, reg.EXACT, reg.LICENCE_REQUIREMENT, "LSEG"),
    ]
    assert acq.access_constraint_established(attempts, REQUIRED, reg.EXACT)[0] is True


# --- item 4 / item 6: licensed file hardening ----------------------------
def _write_licensed(tmp_path, rows, sha=None, row_count=None,
                    start=None, end=None, filename="core.csv"):
    path = tmp_path / filename
    body = "date,value\n" + "".join(f"{d},{v}\n" for d, v in rows)
    path.write_text(body, encoding="utf-8")
    real_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    record = {f: "x" for f in reg.LICENSED_PROVENANCE_FIELDS}
    record.update({
        "original_filename": filename,
        "sha256": sha if sha is not None else real_sha,
        "row_count": row_count if row_count is not None else len(rows),
        "period_start": start if start is not None else rows[0][0],
        "period_end": end if end is not None else rows[-1][0],
    })
    return record, real_sha


ROWS = [("1996-12", "1.0"), ("1997-01", "1.1"), ("1997-02", "1.2")]


def test_complete_provenance_with_a_verified_file_passes(tmp_path):
    record, _ = _write_licensed(tmp_path, ROWS)
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is True, result["failures"]


def test_complete_provenance_without_the_file_never_passes(tmp_path):
    record, _ = _write_licensed(tmp_path, ROWS)
    (tmp_path / record["original_filename"]).unlink()
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is False
    assert result["file_present"] is False
    assert any("not present" in f for f in result["failures"])

    verdict = p4.derive_verdict(
        {"acquired": False, "access_evidence": True, "unavailability_evidence": False},
        INSUFFICIENT, {"present": True, "complete": False,
                       "missing": result["failures"],
                       "file_verification": result},
        POLICY, admissible=True)
    assert verdict["acceptance"] != "PASS"


def test_a_forged_or_stale_hash_never_passes(tmp_path):
    record, _ = _write_licensed(tmp_path, ROWS, sha="0" * 64)
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is False and result["sha256_match"] is False
    assert any("sha256 mismatch" in f for f in result["failures"])


def test_row_count_is_validated_against_the_file(tmp_path):
    record, _ = _write_licensed(tmp_path, ROWS, row_count=999)
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is False and result["row_count_match"] is False


def test_period_bounds_are_validated_against_the_file(tmp_path):
    record, _ = _write_licensed(tmp_path, ROWS, start="1900-01")
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is False and result["period_match"] is False


def test_metadata_completeness_alone_is_never_sufficient(tmp_path):
    """The core of item 4: a perfect record with no file behind it is a claim,
    not evidence."""
    record = {f: "x" for f in reg.LICENSED_PROVENANCE_FIELDS}
    complete, missing = reg.licensed_provenance_complete(record)
    assert complete and not missing          # metadata is complete ...
    result = acq.verify_licensed_file(record, tmp_path)
    assert result["verified"] is False       # ... and it still does not verify


# --- item 5: follow-up fixes ---------------------------------------------
def test_external_dossiers_do_not_fail_the_check_under_a_local_verdict():
    """Previously the check demanded acceptance == BLOCKED_NETWORK, so any
    locally derived verdict would fail it once a dossier existed."""
    external = p4.load_external_findings()
    assert external and all(d["verified_locally"] is False for d in external)
    # derive_verdict's signature proves the dossiers cannot reach the verdict.
    import inspect
    params = set(inspect.signature(p4.derive_verdict).parameters)
    assert params == {"core", "coverage", "licensed", "policy", "admissible"}
    assert "external" not in params


def test_manifest_taxonomy_lists_all_three_specific_verdicts():
    import subprocess
    manifest = json.loads((ROOT / "results" / "phase4" / "run_manifest.json").read_text())
    gates = manifest["gates"]["phase4_acceptance"]
    for verdict in ("FAIL_ACCESS_CONSTRAINT", "FAIL_DATA_UNAVAILABLE",
                    "INCONCLUSIVE_INSUFFICIENT_EVIDENCE"):
        assert verdict in gates, f"{verdict} missing from the manifest taxonomy"
    assert "FAIL" not in gates, "the generic FAIL key must be gone"
    _ = subprocess


def test_no_stale_b5_conflict_text_in_core_transformation():
    t = reg.SERIES_BY_KEY["CORE"].transformation
    assert "EXCLUDED_BY_DESIGN" not in t
    assert "SPECIFICATION_CONFLICTS below" not in t
    assert "EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR" in t

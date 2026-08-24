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


def _core(acquired=False, access=False, unavailable=False):
    return {"acquired": acquired, "access_evidence": access,
            "unavailability_evidence": unavailable}


# --- item 6: the regression that would have caught the bug ---------------
def test_egress_ok_lseg_pages_200_no_licensed_file_yields_access_constraint():
    """egress=true, LSEG historic page 200, LSEG licence evidence 200, no
    licensed file. EXPECT FAIL_ACCESS_CONSTRAINT. FORBID PASS and
    FAIL_DATA_UNAVAILABLE."""
    egress = acq.EgressProbe(True, [], {}, "canary reachable")
    core_sources = reg.SERIES_BY_KEY["CORE"].sources
    lseg = [s for s in core_sources if "LSEG" in s.provider]
    assert len(lseg) >= 2, "CORE needs both a coverage and a licence-terms evidence source"

    outcomes = []
    for source in lseg:
        ok = acq.AttemptResult(url=source.url, outcome=acq.HTTP_OK, http_status=200)
        outcomes.append(acq.classify(ok, egress, source.role, n_observations=0))

    assert all(o == acq.EVIDENCE_CAPTURED for o in outcomes), outcomes
    assert not acq.series_is_acquired(outcomes), "a 200 landing page is not acquisition"
    assert acq.has_access_evidence(outcomes)

    verdict = p4.derive_verdict(
        _core(acquired=acq.series_is_acquired(outcomes),
              access=acq.has_access_evidence(outcomes),
              unavailable=acq.has_unavailability_evidence(outcomes)),
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

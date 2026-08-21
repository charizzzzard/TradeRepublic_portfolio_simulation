"""Phase 4 acquisition, classification and coverage tests.

The load-bearing logic is the guard that stops an environment limitation being
recorded as a research finding. It is tested directly, including the case where
a raw attempt produced something that LOOKS source-specific.
"""
import csv
import sys
from pathlib import Path

import pytest

from portfolio_sim import data_acquisition as acq
from portfolio_sim import data_registry as reg

ROOT = Path(__file__).resolve().parents[1]


def _egress(available: bool) -> acq.EgressProbe:
    return acq.EgressProbe(egress_available=available, attempts=[], proxy_env={},
                           detail="test fixture")


# --- the guard -----------------------------------------------------------
def test_blocked_egress_forces_every_outcome_to_network_blocked():
    """Even a 404 - which would normally be a finding about the source - carries
    no information when nothing could be reached. It must not survive."""
    blocked = _egress(False)
    for raw_outcome in (acq.SOURCE_NOT_FOUND, acq.LICENCE_OR_AUTH_REQUIRED,
                        acq.DATA_INVALID, acq.ACQUIRED):
        attempt = acq.AttemptResult(url="https://x/", outcome=raw_outcome)
        assert acq.classify(attempt, blocked) == acq.NETWORK_BLOCKED


def test_confirmed_egress_lets_source_outcomes_through():
    ok = _egress(True)
    for raw_outcome in (acq.SOURCE_NOT_FOUND, acq.LICENCE_OR_AUTH_REQUIRED,
                        acq.ACQUIRED):
        attempt = acq.AttemptResult(url="https://x/", outcome=raw_outcome)
        assert acq.classify(attempt, ok) == raw_outcome


def test_no_research_verdict_without_egress():
    assert acq.research_verdict_admissible(_egress(False)) is False
    assert acq.research_verdict_admissible(_egress(True)) is True


def test_environment_and_source_outcome_vocabularies_are_disjoint():
    """A single outcome must never be readable as both an infrastructure fact
    and a finding about the world."""
    assert acq.ENVIRONMENT_OUTCOMES.isdisjoint(acq.SOURCE_OUTCOMES)
    assert acq.NETWORK_BLOCKED not in acq.SOURCE_OUTCOMES
    assert acq.ACQUIRED not in acq.ENVIRONMENT_OUTCOMES


def test_canary_hosts_are_not_data_sources():
    """The probe must test hosts unrelated to the data, or a source-specific
    block would be mistaken for a general one."""
    source_urls = {s.url for spec in reg.SERIES for s in spec.sources}
    for canary in acq.CANARY_HOSTS:
        assert canary not in source_urls


# --- manifest rows -------------------------------------------------------
def test_unacquired_rows_carry_empty_provenance_not_placeholders():
    spec = reg.SERIES_BY_KEY["CORE"]
    source = spec.sources[0]
    attempt = acq.AttemptResult(url=source.url, outcome=acq.NETWORK_BLOCKED)
    row = acq.manifest_row("CORE", source, attempt, acq.NETWORK_BLOCKED,
                           spec.transformation, spec.frequency, spec.currency,
                           spec.return_convention)
    assert row["data_status"] == acq.NETWORK_BLOCKED
    assert row["period_start"] == "" and row["period_end"] == ""
    assert row["n_observations"] == 0
    assert row["sha256"] == ""


def test_manifest_csv_has_every_required_provenance_column(tmp_path):
    """PROJECT_META requires source, retrieval date, frequency, currency, return
    convention, start/end, SHA256 and transformations for every series."""
    required = {"source_url", "retrieval_date_utc", "frequency", "currency",
                "return_convention", "period_start", "period_end", "sha256",
                "transformations", "licence_status"}
    assert required <= set(acq.MANIFEST_COLUMNS)
    path = acq.write_manifest_csv([], tmp_path / "data_manifest.csv")
    with path.open() as fh:
        assert set(next(csv.reader(fh))) == set(acq.MANIFEST_COLUMNS)


# --- coverage ------------------------------------------------------------
def test_coverage_insufficient_when_a_required_series_is_missing():
    rows = [{"series_key": "GOLD", "data_status": "ACQUIRED", "n_observations": 500}]
    r = acq.validate_coverage(rows, 360, ("CORE", "GOLD"))
    assert r["result"] == "INSUFFICIENT"
    assert r["missing_series"] == ["CORE"]


def test_coverage_uses_the_shortest_series_not_the_longest():
    rows = [{"series_key": "CORE", "data_status": "ACQUIRED", "n_observations": 600},
            {"series_key": "GOLD", "data_status": "ACQUIRED", "n_observations": 300}]
    r = acq.validate_coverage(rows, 360, ("CORE", "GOLD"))
    assert r["common_months"] == 300
    assert r["result"] == "INSUFFICIENT"


def test_coverage_sufficient_when_all_series_clear_the_requirement():
    rows = [{"series_key": "CORE", "data_status": "ACQUIRED", "n_observations": 400},
            {"series_key": "GOLD", "data_status": "ACQUIRED", "n_observations": 360}]
    assert acq.validate_coverage(rows, 360, ("CORE", "GOLD"))["result"] == "SUFFICIENT"


def test_unacquired_rows_do_not_count_toward_coverage():
    rows = [{"series_key": "CORE", "data_status": "NETWORK_BLOCKED", "n_observations": 999}]
    assert acq.validate_coverage(rows, 360, ("CORE",))["result"] == "INSUFFICIENT"


# --- effective sample size ----------------------------------------------
def test_effective_sample_size_reproduces_the_project_meta_figure():
    """PROJECT_META: ~1.5 independent observations from 50y of 20y windows.
    (50 - 20) / 20 = 1.5, against (50 - 20) * 12 + 1 = 361 overlapping windows."""
    e = acq.effective_sample_size(50, 20)
    assert e["independent_increments_T_minus_h_over_h"] == pytest.approx(1.5)
    assert e["overlapping_monthly_windows"] == 361
    assert e["non_overlapping_windows_floor"] == 2
    assert e["non_overlapping_windows_exact"] == pytest.approx(2.5)


def test_effective_sample_size_ten_year_windows():
    e = acq.effective_sample_size(50, 10)
    assert e["independent_increments_T_minus_h_over_h"] == pytest.approx(4.0)
    assert e["overlapping_monthly_windows"] == 481


def test_effective_sample_size_rejects_nonsense():
    with pytest.raises(ValueError):
        acq.effective_sample_size(50, 0)


# --- registry integrity --------------------------------------------------
def test_core_is_the_only_stop_condition():
    assert reg.STOP_IF_MISSING == ("CORE",)
    assert "CORE" in reg.REDUCED_UNIVERSE


def test_every_series_declares_at_least_one_source_and_a_transformation():
    for spec in reg.SERIES:
        assert spec.sources, f"{spec.key} has no source"
        assert spec.transformation.strip(), f"{spec.key} has no transformation"
        assert spec.frequency and spec.currency and spec.return_convention


def test_every_source_declares_a_licence_status():
    allowed = {"OPEN", "LICENCE_REQUIRED", "LICENCE_UNKNOWN"}
    for spec in reg.SERIES:
        for s in spec.sources:
            assert s.licence_status in allowed, f"{spec.key}/{s.provider}"


def test_every_endpoint_is_marked_unverified_while_there_is_no_egress():
    """No URL in the registry has been confirmed to resolve, and the registry
    must say so rather than implying validation that did not happen."""
    for spec in reg.SERIES:
        for s in spec.sources:
            assert s.endpoint_status == "UNVERIFIED"


def test_source_tiers_follow_the_project_meta_priority_scale():
    for spec in reg.SERIES:
        for s in spec.sources:
            assert 1 <= s.tier <= 5


def test_core_proxy_candidate_is_flagged_as_not_acwi():
    """A developed-markets factor file must never quietly stand in for ACWI."""
    core = reg.SERIES_BY_KEY["CORE"]
    proxy = [s for s in core.sources if s.tier == 4]
    assert proxy, "CORE should record an academic fallback candidate"
    note = proxy[0].note.upper()
    assert "NOT ACWI" in note and "SPLICE" in note


def test_all_ten_universe_instruments_have_a_cost_source():
    from portfolio_sim import config
    universe = set(config.load("assets")["instruments"])
    assert {c.instrument for c in reg.COST_SOURCES} == universe


# --- external findings dossier -------------------------------------------
def _load_runner():
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_phase4
    return run_phase4


def test_external_findings_are_recorded_as_unverified():
    """Dossiers produced somewhere this session cannot reach are evidence, not
    results. Each must carry verified_locally=False and a file hash."""
    p4 = _load_runner()
    ext = p4.load_external_findings()
    assert ext, "external findings dossiers should be present"
    assert len(ext) >= 2, "both acquisition rounds should be recorded"
    for d in ext:
        assert d["verified_locally"] is False
        assert len(d["file_sha256"]) == 64
    assert sorted(d["round"] for d in ext) == [1, 2]


def test_no_dossier_claims_materialised_artifacts():
    """No hash or row count was produced externally, so nothing may claim one."""
    p4 = _load_runner()
    for d in p4.load_external_findings():
        assert d["artifacts_materialised"] is False


def test_candidate_verdict_is_never_the_acceptance_value():
    """The projection must be structurally distinguishable from the finding."""
    p4 = _load_runner()
    cv = p4.candidate_verdict(p4.load_external_findings())
    assert cv["candidate"] not in ("PASS", "PARTIAL", "FAIL", "BLOCKED_NETWORK")
    assert cv["blocked_by"], "a candidate verdict must state what blocks issuing it"


def test_candidate_verdict_preserves_licence_vs_nonexistence():
    """A FAIL on licence grounds is a statement about this project's own
    open-reproducibility condition, not about whether the data exists."""
    p4 = _load_runner()
    cv = p4.candidate_verdict(p4.load_external_findings())
    d = cv["critical_distinction"].lower()
    assert "does not exist" in d and "redistribute" in d


def test_core_registry_target_is_ftse_all_world_net_return_usd():
    """IE00BK5BQT80 tracks FTSE All-World NR USD. Two earlier registry errors:
    the wrong index (MSCI ACWI) and the wrong currency (EUR, taken from the
    trading currency rather than the benchmark)."""
    core = reg.SERIES_BY_KEY["CORE"]
    assert "FTSE All-World" in core.description
    assert core.currency == "USD", "benchmark currency is USD, not the trading currency"
    ftse = next(s for s in core.sources if "FTSE Russell" in s.provider)
    assert ftse.tier == 1 and ftse.licence_status == "LICENCE_REQUIRED"
    msci = next(s for s in core.sources if s.provider == "MSCI")
    assert "not the index" in msci.note.lower()


def test_vanguard_nav_fallback_is_marked_insufficient():
    core = reg.SERIES_BY_KEY["CORE"]
    nav = next(s for s in core.sources if "Vanguard" in s.provider)
    assert "INSUFFICIENT_HISTORY" in nav.note
    assert "2019" in nav.note, "share class inception must be recorded"


def test_gold_open_proxy_is_registered_with_its_difference_stated():
    """The World Bank series is admissible but is a monthly AVERAGE, not a
    month-end value - which matters for a claim resting on second moments."""
    gold = reg.SERIES_BY_KEY["GOLD"]
    wb = next(s for s in gold.sources if "World Bank" in s.provider)
    assert wb.licence_status == "OPEN"
    note = wb.note
    assert "CC BY 4.0" in note
    assert "AVERAGE" in note and "MONTH-END" in note
    assert "may not stand in silently" in note.lower()


def test_gold_exact_source_remains_licence_required():
    gold = reg.SERIES_BY_KEY["GOLD"]
    lbma = next(s for s in gold.sources if "LBMA" in s.provider)
    assert lbma.licence_status == "LICENCE_REQUIRED"


def test_wt3230_is_recorded_as_a_specification_error_not_a_rename():
    """The official migration catalogue has no entry for BBK01.WT3230, and the
    candidate succeeds WU9555/WU0115 instead."""
    spec = reg.SERIES_BY_KEY["BUND_LONG_YIELD"]
    assert "SPECIFICATION_ERROR_SUSPECTED" in spec.blocker
    note = spec.sources[0].note
    assert "WU9555" in note and "NOT of WT3230" in note
    assert "MAPPING FROM WT3230 NOT SUPPORTED" in note


def test_eonia_splice_rule_is_documented_and_not_silent():
    """PROJECT_META forbids spliced series without a documented splice rule."""
    t = reg.SERIES_BY_KEY["SHORT_RATE_EA"].transformation
    assert "SPLICE" in t and "8.5 bp" in t and "never" in t.lower()


def test_hicp_key_migrated_off_the_discontinued_series():
    spec = reg.SERIES_BY_KEY["HICP_EA"]
    urls = " ".join(s.url for s in spec.sources)
    assert "4D0.ANR" in urls, "must use the current HICP key"
    assert "ICP/M.U2.N.000000.4.ANR" not in urls, "discontinued key must be gone"


def test_fx_specification_conflict_was_surfaced_then_resolved_by_the_operator():
    """The conflict must remain visible with its resolution recorded - deleting
    it would erase the reason the decision was taken."""
    conflict = next(c for c in reg.SPECIFICATION_CONFLICTS
                    if c["id"] == "B5_FX_VS_USD_BENCHMARK")
    assert conflict["status"] == "RESOLVED"
    assert conflict["severity"] == "DECISION_RELEVANT"
    assert conflict["resolved_by"] == "human_operator"
    assert "MUST be converted to EUR" in conflict["resolution"]
    # The original conflict statement and damage scope stay on the record.
    assert "Phases 1-3 are NOT invalidated" in conflict["scope_of_damage"]
    assert len(conflict["resolution_options"]) >= 2


def test_fx_conflict_was_resolved_by_the_operator_not_silently():
    """B.5 is a first-class assumption, so the conflict was surfaced and left to
    the operator, who resolved it on 2026-08-21. The revised file must record
    WHAT changed and WHY, not merely carry a new value."""
    from portfolio_sim import config
    fx = config.load("fx")
    assert fx["status"] == "EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR"
    assert fx["supersedes_status"] == "EXCLUDED_BY_DESIGN"
    assert fx["decided_by"] == "human_operator"
    assert "OMITS FX" in fx["revision_reason"]
    # The resolution keeps option_b's motivation: no stochastic FX factor.
    assert fx["decision"] == "option_b"
    assert fx["simulation"]["no_separate_fx_factor"] is True


def test_costs_config_still_flags_placeholders_until_ter_is_verified():
    """TER values were reported externally but not verified or hashed here, so
    config/costs.json must not yet claim to be sourced."""
    import json
    costs = json.loads((ROOT / "config" / "costs.json").read_text())
    assert costs["data_status"] == "PLACEHOLDER_NOT_SOURCED"

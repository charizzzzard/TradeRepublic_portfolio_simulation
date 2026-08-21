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

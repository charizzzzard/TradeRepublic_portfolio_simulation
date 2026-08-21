"""Predecessor-gate tests.

Teil C forbids starting a phase whose predecessor gate is not PASS. These check
that the guard actually refuses, rather than merely reporting.
"""
import json

import pytest

from portfolio_sim import gates
from portfolio_sim.hashing import REPO_ROOT, parameter_hash

PHASE1 = REPO_ROOT / "results" / "phase1" / "run_manifest.json"
PHASE1_NAME = "PHASE_1_R2F_DECISION_PATH_CLEANUP"


@pytest.fixture
def manifest_copy(tmp_path):
    def _make(**overrides):
        man = json.loads(PHASE1.read_text())
        extra_overrides = overrides.pop("extra", None)
        man.update(overrides)
        if extra_overrides:
            man["extra"].update(extra_overrides)
        path = tmp_path / "run_manifest.json"
        path.write_text(json.dumps(man))
        return path
    return _make


@pytest.mark.phase_artifact
def test_real_phase1_manifest_passes_the_gate():
    rec = gates.require_phase_pass(PHASE1, PHASE1_NAME)
    assert rec["predecessor_acceptance"] == "PASS"
    assert rec["parameter_hash_stable"] is True


def test_missing_manifest_is_a_gate_failure(tmp_path):
    with pytest.raises(gates.GateFailure, match="not found"):
        gates.require_phase_pass(tmp_path / "nope.json", PHASE1_NAME)


@pytest.mark.phase_artifact
def test_failed_acceptance_blocks_the_dependent_phase(manifest_copy):
    path = manifest_copy(extra={"acceptance": "FAIL"})
    with pytest.raises(gates.GateFailure, match="not PASS"):
        gates.require_phase_pass(path, PHASE1_NAME)


@pytest.mark.phase_artifact
def test_absent_acceptance_field_blocks_the_dependent_phase(tmp_path):
    """A manifest with no acceptance record must not be read as a pass."""
    man = json.loads(PHASE1.read_text())
    man["extra"].pop("acceptance")
    path = tmp_path / "run_manifest.json"
    path.write_text(json.dumps(man))
    with pytest.raises(gates.GateFailure, match="not PASS"):
        gates.require_phase_pass(path, PHASE1_NAME)


@pytest.mark.phase_artifact
def test_wrong_phase_is_rejected(manifest_copy):
    path = manifest_copy(phase="PHASE_9_SOMETHING_ELSE")
    with pytest.raises(gates.GateFailure, match="expected"):
        gates.require_phase_pass(path, PHASE1_NAME)


@pytest.mark.phase_artifact
def test_numeric_config_drift_blocks_the_dependent_phase(manifest_copy):
    """Drift in a config that enters the computation invalidates the predecessor's
    results, so the gate must refuse."""
    path = manifest_copy(numeric_parameter_hash="0" * 64)
    with pytest.raises(gates.GateFailure, match="numeric parameter drift"):
        gates.require_phase_pass(path, PHASE1_NAME)


@pytest.mark.phase_artifact
def test_documentary_config_drift_does_not_block_but_is_recorded(manifest_copy):
    """Drift confined to configs no computation reads must NOT invalidate results,
    but must still be visible in the gate record.

    The exemption is safe only because tests/test_config_separation.py
    demonstrates by mutation that those files move no number.
    """
    path = manifest_copy(parameter_hash="0" * 64)
    rec = gates.require_phase_pass(path, PHASE1_NAME)
    assert rec["numeric_parameter_hash_stable"] is True
    assert rec["documentary_parameter_drift"]["detected"] is True
    assert rec["documentary_parameter_drift"]["invalidates_results"] is False


@pytest.mark.phase_artifact
def test_manifest_without_a_numeric_hash_falls_back_to_the_strict_comparison(manifest_copy):
    """A manifest written before the split records no numeric hash. The gate must
    then use the full hash, which is stricter, rather than skipping the check."""
    import json
    path = manifest_copy(parameter_hash="0" * 64)
    man = json.loads(path.read_text())
    man.pop("numeric_parameter_hash", None)
    path.write_text(json.dumps(man))
    with pytest.raises(gates.GateFailure, match="parameter_hash drift"):
        gates.require_phase_pass(path, PHASE1_NAME)


def test_convention_modules_are_unchanged_since_the_pinned_baseline():
    """Requirement: no existing engine convention may be modified.

    Adding a new module is allowed; changing one that carries the A.5 frozen
    conventions is not.
    """
    result = gates.verify_conventions_unchanged("HEAD")
    assert result["result"] == "PASS", result
    assert set(gates.CONVENTION_MODULES) <= set(result["modules_verified"])


def test_unresolvable_baseline_ref_is_a_failure_not_a_pass():
    result = gates.verify_conventions_unchanged("not-a-real-ref")
    assert result["result"] == "FAIL"


def test_parameter_hash_is_stable_across_calls():
    assert parameter_hash() == parameter_hash()

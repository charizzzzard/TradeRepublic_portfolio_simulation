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


def test_real_phase1_manifest_passes_the_gate():
    rec = gates.require_phase_pass(PHASE1, PHASE1_NAME)
    assert rec["predecessor_acceptance"] == "PASS"
    assert rec["parameter_hash_stable"] is True


def test_missing_manifest_is_a_gate_failure(tmp_path):
    with pytest.raises(gates.GateFailure, match="not found"):
        gates.require_phase_pass(tmp_path / "nope.json", PHASE1_NAME)


def test_failed_acceptance_blocks_the_dependent_phase(manifest_copy):
    path = manifest_copy(extra={"acceptance": "FAIL"})
    with pytest.raises(gates.GateFailure, match="not PASS"):
        gates.require_phase_pass(path, PHASE1_NAME)


def test_absent_acceptance_field_blocks_the_dependent_phase(tmp_path):
    """A manifest with no acceptance record must not be read as a pass."""
    man = json.loads(PHASE1.read_text())
    man["extra"].pop("acceptance")
    path = tmp_path / "run_manifest.json"
    path.write_text(json.dumps(man))
    with pytest.raises(gates.GateFailure, match="not PASS"):
        gates.require_phase_pass(path, PHASE1_NAME)


def test_wrong_phase_is_rejected(manifest_copy):
    path = manifest_copy(phase="PHASE_9_SOMETHING_ELSE")
    with pytest.raises(gates.GateFailure, match="expected"):
        gates.require_phase_pass(path, PHASE1_NAME)


def test_config_drift_blocks_the_dependent_phase(manifest_copy):
    """If config/ changed since the predecessor ran, its PASS no longer applies."""
    path = manifest_copy(parameter_hash="0" * 64)
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

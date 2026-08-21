"""Predecessor-phase gates.

Teil C: "Kein Start einer Phase, deren Vorgaengergate nicht PASS ist."

`manifest.assert_no_stage_skip` polices the GOVERNANCE STATUS LADDER - it stops
DISCOVERY jumping to POLICY_CANDIDATE. It says nothing about whether the
previous phase's run actually passed its acceptance checks. Those are two
different guarantees, and only the first was enforced in code after Phase 1.
This module supplies the second.

Three things are verified before a dependent phase may start:

  1. the predecessor's manifest exists, is for the expected phase, and recorded
     `extra.acceptance == PASS`;
  2. `parameter_hash` still matches, i.e. no config changed underneath it;
  3. every source module that existed at the pinned baseline commit is still
     byte-identical. Adding a NEW module is allowed; modifying an existing one
     is not, because the frozen conventions of A.5 live inside them.

A check that cannot be performed is a FAIL, not a pass with a caveat
(Teil D: reproducibility FAIL -> STOP).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from .hashing import (NON_NUMERIC_CONFIGS, REPO_ROOT, numeric_parameter_hash,
                      parameter_hash, sha256_bytes)

# Modules that carry the frozen conventions of A.5 and the Teil B tax
# decisions. Listed explicitly so that adding a module to this package is a
# deliberate act rather than something the glob quietly absorbs.
CONVENTION_MODULES = (
    "src/portfolio_sim/engine.py",
    "src/portfolio_sim/tax_engine.py",
    "src/portfolio_sim/position.py",
    "src/portfolio_sim/costs.py",
    "src/portfolio_sim/macro.py",
    "src/portfolio_sim/rng.py",
    "src/portfolio_sim/metrics.py",
)


class GateFailure(RuntimeError):
    """Raised when a predecessor gate does not pass. Callers must STOP."""


def _repo_relative(path: Path) -> str:
    """Repo-relative path for the record, falling back to absolute.

    A manifest handed in from outside the repository is a legitimate call (a
    test fixture, a manifest copied for inspection) and must not crash the gate.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _git(*args: str) -> tuple[int, bytes]:
    proc = subprocess.run(["git", "-C", str(REPO_ROOT), *args],
                          capture_output=True, timeout=30)
    return proc.returncode, proc.stdout


def verify_conventions_unchanged(baseline_ref: str) -> dict:
    """Check that every convention-bearing module matches `baseline_ref`.

    Requirement 3 of the Phase 2 work order ("keine bestehenden
    Engine-Konventionen veraendern") is otherwise only a promise. This turns it
    into something a later reader can re-check.
    """
    rc, _ = _git("rev-parse", "--verify", f"{baseline_ref}^{{commit}}")
    if rc != 0:
        return {"result": "FAIL", "reason": f"baseline ref {baseline_ref} not resolvable"}

    modified, missing = [], []
    for rel in CONVENTION_MODULES:
        rc, blob = _git("show", f"{baseline_ref}:{rel}")
        if rc != 0:
            missing.append(rel)
            continue
        current = (REPO_ROOT / rel).read_bytes()
        if sha256_bytes(current) != sha256_bytes(blob):
            modified.append(rel)

    if missing or modified:
        return {"result": "FAIL", "modified": modified, "missing_at_baseline": missing}
    return {
        "result": "PASS",
        "baseline_ref": baseline_ref,
        "modules_verified": list(CONVENTION_MODULES),
        "detail": "all convention-bearing modules byte-identical to the pinned baseline",
    }


def require_phase_pass(manifest_path: Path, expected_phase: str,
                       baseline_ref: str | None = None) -> dict:
    """Validate a predecessor phase manifest, or raise GateFailure.

    Returns a structured record for embedding in the dependent phase's own
    manifest, so the chain of gates is auditable from the results alone.
    """
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.exists():
        raise GateFailure(
            f"predecessor manifest not found: {manifest_path}. "
            "Teil C: no phase may start whose predecessor gate is not PASS."
        )

    man = json.loads(manifest_path.read_text(encoding="utf-8"))

    if man.get("phase") != expected_phase:
        raise GateFailure(
            f"manifest at {manifest_path} is for phase {man.get('phase')!r}, "
            f"expected {expected_phase!r}."
        )

    acceptance = man.get("extra", {}).get("acceptance")
    if acceptance != "PASS":
        raise GateFailure(
            f"predecessor {expected_phase} recorded acceptance={acceptance!r}, not PASS. "
            "STOP: no dependent phase may run."
        )

    record = {
        "predecessor_phase": expected_phase,
        "predecessor_manifest": _repo_relative(manifest_path),
        "predecessor_acceptance": acceptance,
        "predecessor_git_sha": man.get("git_sha"),
        "predecessor_code_hash": man.get("code_hash"),
        "predecessor_parameter_hash": man.get("parameter_hash"),
        "predecessor_status": man.get("status"),
    }

    current_params = parameter_hash()
    current_numeric = numeric_parameter_hash()
    record["current_parameter_hash"] = current_params
    record["current_numeric_parameter_hash"] = current_numeric

    # Hard failure only on drift that can move a number. A predecessor manifest
    # written before the split records no numeric hash; in that case fall back
    # to the full hash, which is the stricter comparison.
    predecessor_numeric = man.get("numeric_parameter_hash")
    if predecessor_numeric is not None:
        if current_numeric != predecessor_numeric:
            raise GateFailure(
                "numeric parameter drift: a config that enters the computation changed "
                f"since the predecessor phase ({predecessor_numeric} -> {current_numeric}). "
                "The predecessor's results no longer describe the current configuration."
            )
        record["numeric_parameter_hash_stable"] = True
        if current_params != man.get("parameter_hash"):
            record["documentary_parameter_drift"] = {
                "detected": True,
                "configs_that_may_have_changed": list(NON_NUMERIC_CONFIGS),
                "invalidates_results": False,
                "reason": "Only configs outside the numeric path differ. No computation "
                          "reads them, so no recorded result changes. This is verified by "
                          "tests/test_config_separation.py, not assumed.",
            }
    else:
        if current_params != man.get("parameter_hash"):
            raise GateFailure(
                "parameter_hash drift: config/ changed since the predecessor phase "
                f"({man.get('parameter_hash')} -> {current_params}). "
                "A dependent phase may not run against altered configuration."
            )
    record["parameter_hash_stable"] = current_params == man.get("parameter_hash")

    if baseline_ref is not None:
        conv = verify_conventions_unchanged(baseline_ref)
        record["convention_immutability"] = conv
        if conv["result"] != "PASS":
            raise GateFailure(f"engine conventions changed since {baseline_ref}: {conv}")

    return record

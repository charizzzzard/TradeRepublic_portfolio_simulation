"""run_manifest.json - no result without a manifest (Teil C).

The manifest is the only thing that makes a number in this project citable. It
records what code, what parameters, what data and what environment produced a
result, plus the governance status that result is allowed to carry.

Gate thresholds are hashed here BEFORE the run (Phase 6 Gate-Freeze), so a
later edit to a threshold is technically detectable.
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

from . import BASELINE_ID, __version__
from .config import all_configs, load
from .hashing import (canonical_json, code_hash, environment_hash, git_sha,
                      parameter_hash, sha256_obj)

STATUS_LADDER = (
    "DISCOVERY",
    "CALIBRATED_DISCOVERY",
    "MODEL_CONSISTENT_FINDING",
    "EMPIRICAL_SUPPORT",
    "POLICY_CANDIDATE",
    "HUMAN_DECISION",
)

# Which engine may award which status. Engine B/C can never exceed
# MODEL_CONSISTENT_FINDING; only Engine A (real historical data) can award
# EMPIRICAL_SUPPORT.
MAX_STATUS_BY_ENGINE = {
    "C": "MODEL_CONSISTENT_FINDING",
    "B": "MODEL_CONSISTENT_FINDING",
    "A": "EMPIRICAL_SUPPORT",
}


def assert_no_stage_skip(previous: str, proposed: str) -> None:
    if previous not in STATUS_LADDER or proposed not in STATUS_LADDER:
        raise ValueError(f"unknown status: {previous} -> {proposed}")
    i, j = STATUS_LADDER.index(previous), STATUS_LADDER.index(proposed)
    if j > i + 1:
        raise ValueError(
            f"stage skip forbidden (Teil A.3): {previous} -> {proposed}. "
            f"Next allowed stage is {STATUS_LADDER[i + 1]}."
        )


def assert_status_allowed_for_engine(engine: str, proposed: str) -> None:
    cap = MAX_STATUS_BY_ENGINE[engine]
    if STATUS_LADDER.index(proposed) > STATUS_LADDER.index(cap):
        raise ValueError(
            f"Engine {engine} may not award {proposed}; its ceiling is {cap}. "
            "MODEL_CONSISTENT_FINDING != EMPIRICAL_SUPPORT != POLICY."
        )


def gate_freeze_hash(gates: dict) -> str:
    return sha256_obj(gates)


def build(
    run_id: str,
    phase: str,
    n_parameter_worlds: int,
    n_paths_per_world: int,
    portfolio_definitions: dict,
    status: str = "DISCOVERY",
    engine: str = "C",
    gates: dict | None = None,
    data_manifest_hash: str = "NO_EMPIRICAL_DATA_LOADED",
    extra: dict | None = None,
) -> dict:
    assert_status_allowed_for_engine(engine, status)
    cfg = all_configs()
    manifest = {
        "run_id": run_id,
        "phase": phase,
        "timestamp_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "package_version": __version__,
        "baseline_id": BASELINE_ID,
        "git_sha": git_sha(),
        "seed": cfg["conventions"]["seed"],
        "code_hash": code_hash(),
        "parameter_hash": parameter_hash(),
        "data_hash": data_manifest_hash,
        "environment_hash": environment_hash(),
        "n_parameter_worlds": n_parameter_worlds,
        "n_paths_per_world": n_paths_per_world,
        "effective_n_for_parameter_claims": n_parameter_worlds,
        "portfolio_definitions": portfolio_definitions,
        "tax_config": cfg["tax"],
        "costs_config": cfg["costs"],
        "inflation_config": {
            "model": "Ornstein-Uhlenbeck, monthly, coupled to the short rate",
            "note": "B.2: the Basiszins is a function of the modelled short rate, floored at 0.",
        },
        "rebalancing_config": cfg["conventions"]["rebalancing"],
        "fx_config": cfg["fx"],
        "engine": engine,
        "engine_status_ceiling": MAX_STATUS_BY_ENGINE[engine],
        "status": status,
        "promotion_allowed": False,
        "human_final_decision": True,
        "epistemic_limits_ack": ["G1", "G2", "G3", "G4", "G5", "G6", "G7"],
        "b1_withholding_credit_status": cfg["tax"]["withholding_tax_credit"]["status"],
        "b5_fx_disclosure": cfg["fx"]["cost_borne"],
        "unmodelled_boundary_conditions": (
            "Emergency fund, human capital, statutory/occupational pension, liquidity "
            "events and interim withdrawals are NOT modelled (B.6). This is a partial "
            "analysis of portfolio allocation, not financial planning."
        ),
    }
    if gates is not None:
        manifest["gates"] = gates
        manifest["gate_freeze_hash"] = gate_freeze_hash(gates)
    if extra:
        manifest["extra"] = extra
    return manifest


def write(manifest: dict, path: Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return path

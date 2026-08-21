"""Falsification ledger.

A claim enters the ledger BEFORE it is tested, with its metric, its threshold
and its required probability already fixed. Claims that G1 shows to be
undecidable with the available data are entered as INDETERMINATE_BY_CONSTRUCTION
and never receive a confirmatory run. That is a documented research conclusion,
not an evasion.
"""
from __future__ import annotations

import json
from pathlib import Path

from .hashing import REPO_ROOT, sha256_obj

LEDGER_PATH = REPO_ROOT / "results" / "falsification_ledger.json"

# G1 arithmetic, recomputed rather than quoted. See scripts/verify_g1.py.
G1 = {
    "median_real_terminal_reference_eur": 199000,
    "materiality_gate_eur": 5000,
    "implied_portfolio_cagr_pp_per_year": 0.1242,
    "required_satellite_excess_pp_per_year": {"sleeve_15pct": 0.828, "sleeve_5pct": 2.483},
    "se_of_return_difference_pp_per_year": {"rho_0.95": 0.805, "rho_0.70": 1.972},
    "conclusion": (
        "The required satellite excess return lies INSIDE the standard error of the "
        "underlying return difference estimated from 50 years of history. Expected-value "
        "driven satellite claims are therefore structurally undecidable with the available "
        "data."
    ),
}

INDETERMINATE_SATELLITES = ("SP500", "NASDAQ", "EUROPE", "DAX", "JAPAN", "EM", "COMMOD", "DIVIDEND")


def indeterminate_entry(asset: str) -> dict:
    return {
        "claim_id": f"satellite_excess_{asset.lower()}",
        "asset": asset,
        "status": "INDETERMINATE_BY_CONSTRUCTION",
        "confirmatory_run": "NOT_PERFORMED_BY_DESIGN",
        "rationale": (
            "The required effect (0.83-2.48 pp/year satellite excess, depending on sleeve "
            "size) lies within the standard error of the underlying return difference "
            "(0.80-1.97 pp/year). A confirmatory run cannot decide this claim."
        ),
        "epistemic_limit": "G1",
        "reporting_rule": (
            "No statement about this asset's expected-return advantage may appear in any "
            "report. Reproducing the R0/D1-D4 rank ordering for it is ASSUMPTION_ECHO (G3), "
            "not evidence."
        ),
    }


GOLD_CLAIM = {
    "claim_id": "gold_downside_r8g",
    "claim": (
        "A gold sleeve materially reduces portfolio downside against a 100% global equity "
        "core, WITHOUT any return assumption in gold's favour."
    ),
    "status": "DISCOVERY",
    "tested_in_phase": "PHASE_6",
    "mu_neutrality": {
        "primary": 0.0,
        "sensitivity": "= core_mu",
        "forbidden": "Any gold mu assumption implying a return advantage.",
        "rationale": "G2: only second moments and tax/cost mechanics are decidable.",
    },
    "candidate_weights": [0.05, 0.10, 0.15],
    "primary_metric": "paired_max_drawdown_delta",
    "secondary_metric": "paired_real_terminal_wealth_delta",
    "gates": {
        "wealth_gate": {
            "metric": "paired_real_terminal_wealth_delta",
            "materiality": "median_delta >= 3.0% of the core median terminal value of the same cell",
            "joint_condition": "median_delta >= materiality AND P_model(delta > 0) >= 0.60",
            "and_is_mandatory": (
                "Without the AND, a candidate with a 60% hit rate and a median delta near "
                "zero would pass."
            ),
        },
        "downside_gate": {
            "metric": "paired_max_drawdown_delta",
            "joint_condition": "median_improvement >= 2pp AND P_model(improvement >= 2pp) >= 0.65",
        },
        "parameter_gate": "A majority of parameter worlds must show the same advantage.",
        "model_gate": "The advantage must not exist in only one model family.",
    },
    "tax_variants": ["B3_assumed", "B3_alternative"],
    "path_budget": {"n_parameter_worlds": 400, "n_paths_per_world": 500,
                    "rationale": "SE(win rate) = 2.24pp at 500 paths vs 3.16pp at 250; the gate "
                                 "compares 60% against 50%."},
    "required_model_robustness": (
        "While Engine A and Engine B are unavailable, the maximum attainable stage is "
        "MODEL_CONSISTENT_FINDING. No promotion."
    ),
}


def build() -> dict:
    return {
        "schema_version": "1.0.0",
        "hypotheses": {
            "H0": "100% global core remains the best non-falsified baseline.",
            "H1": "The satellite produces a material, robust portfolio effect that survives "
                  "path, parameter and model uncertainty.",
            "admissible_conclusion": "No tested satellite delivers sufficiently robust "
                                     "incremental decision utility against a 100% global core.",
        },
        "g1_arithmetic": G1,
        "tested_claims": [GOLD_CLAIM],
        "indeterminate_claims": [indeterminate_entry(a) for a in INDETERMINATE_SATELLITES],
    }


def write(path: Path = LEDGER_PATH) -> Path:
    payload = build()
    payload["ledger_hash"] = sha256_obj(payload)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    return path

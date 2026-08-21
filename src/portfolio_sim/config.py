"""Configuration loading. Configs are data, never code, and are hashed as data."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .hashing import REPO_ROOT

CONFIG_DIR = REPO_ROOT / "config"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    return json.loads((CONFIG_DIR / f"{name}.json").read_text(encoding="utf-8"))


def all_configs() -> dict:
    return {
        n: load(n)
        for n in ("investor", "conventions", "tax", "costs", "fx", "assets")
    }


def assert_fx_decision_present() -> dict:
    """B.5: an explicit FX decision must exist. Silent omission is disallowed."""
    fx = load("fx")
    if fx.get("decision") not in ("option_a", "option_b"):
        raise ValueError(
            "B.5 violation: config/fx.json must declare decision=option_a or option_b."
        )
    return fx

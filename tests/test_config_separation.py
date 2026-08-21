"""The numeric / documentary config split must be demonstrated, not assumed.

`gates.require_phase_pass` fails hard only on drift in configs that can move a
number, and treats drift in `fx.json` / `data_policy.json` as documentary. That
is a load-bearing exemption: if it were wrong, a change to a decision file could
silently invalidate frozen results while every gate still reported PASS.

So it is tested by actually mutating those files on disk and showing the
simulation output is bit-identical.
"""
import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from portfolio_sim import config
from portfolio_sim.engine import AssetParams, PortfolioSpec, RunSpec, simulate
from portfolio_sim.hashing import (NON_NUMERIC_CONFIGS, NUMERIC_CONFIGS, REPO_ROOT,
                                   numeric_parameter_hash, parameter_hash)
from portfolio_sim.rng import CRNBlock, full_corr_from

CONFIG_DIR = REPO_ROOT / "config"


def _reference_run():
    config.load.cache_clear()
    tax, costs = config.load("tax"), config.load("costs")
    crn = CRNBlock(config.load("conventions")["seed"], 0, 200, 120)
    return simulate(PortfolioSpec("CORE_100", {"CORE": 1.0}),
                    {"CORE": AssetParams(g=0.055, vol=0.16)},
                    full_corr_from({}), crn, RunSpec(horizon_years=10), tax, costs)


@pytest.fixture
def restore_configs():
    backup = {n: (CONFIG_DIR / f"{n}.json").read_bytes() for n in NON_NUMERIC_CONFIGS}
    yield
    for name, data in backup.items():
        (CONFIG_DIR / f"{name}.json").write_bytes(data)
    config.load.cache_clear()


def test_every_config_is_classified_exactly_once():
    on_disk = {p.stem for p in CONFIG_DIR.glob("*.json")}
    classified = set(NUMERIC_CONFIGS) | set(NON_NUMERIC_CONFIGS)
    assert on_disk == classified, f"unclassified config files: {on_disk ^ classified}"
    assert not (set(NUMERIC_CONFIGS) & set(NON_NUMERIC_CONFIGS))


@pytest.mark.parametrize("name", NON_NUMERIC_CONFIGS)
def test_mutating_a_documentary_config_changes_no_number(name, restore_configs):
    """The actual demonstration: mutate the file, re-run, require bit equality."""
    before = _reference_run()

    path = CONFIG_DIR / f"{name}.json"
    payload = json.loads(path.read_text())
    payload["_mutation_probe"] = "this value must not reach any computation"
    path.write_text(json.dumps(payload, indent=2))

    after = _reference_run()
    for key in ("terminal_real_after_tax", "terminal_nominal_after_tax",
                "terminal_real_pretax", "tax_paid_nominal", "value_path_nominal",
                "contributions_nominal"):
        assert np.array_equal(before[key], after[key]), (
            f"mutating config/{name}.json moved {key} - it is NOT documentary and must "
            "be reclassified as numeric"
        )


@pytest.mark.parametrize("name", NON_NUMERIC_CONFIGS)
def test_documentary_drift_moves_the_full_hash_but_not_the_numeric_hash(name, restore_configs):
    numeric_before, full_before = numeric_parameter_hash(), parameter_hash()

    path = CONFIG_DIR / f"{name}.json"
    payload = json.loads(path.read_text())
    payload["_mutation_probe"] = "probe"
    path.write_text(json.dumps(payload, indent=2))

    assert numeric_parameter_hash() == numeric_before, "numeric hash must be unaffected"
    assert parameter_hash() != full_before, "full hash must still detect the change"


def test_numeric_config_drift_is_caught_by_the_numeric_hash(tmp_path):
    """The converse: a numeric config change MUST move the numeric hash."""
    name = "tax"
    path = CONFIG_DIR / f"{name}.json"
    backup = path.read_bytes()
    before = numeric_parameter_hash()
    try:
        payload = json.loads(path.read_text())
        payload["_mutation_probe"] = "probe"
        path.write_text(json.dumps(payload, indent=2))
        assert numeric_parameter_hash() != before
    finally:
        path.write_bytes(backup)
        config.load.cache_clear()


def test_fx_decision_records_the_mandatory_eur_conversion_rule():
    """B.5 revised: no separate stochastic FX factor, but non-EUR calibration
    series MUST be converted to EUR before estimation."""
    fx = config.load("fx")
    assert fx["status"] == "EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR"
    assert fx["simulation"]["no_separate_fx_factor"] is True
    rule = fx["historical_calibration"]["rule"]
    assert "MANDATORY" in rule and "EUR" in rule
    assert "fx_quote_convention" in fx["historical_calibration"]
    assert any("Isolated FX risk" in c for c in fx["unsupported_claims"])


def test_data_policy_separates_the_three_dimensions():
    policy = config.load("data_policy")
    assert set(policy["dimensions"]) == {
        "availability_status", "redistribution_status", "reproducibility_status"}
    assert "reproducibility != redistribution" in policy["core_principle"]
    assert "LICENSED_REPRODUCIBLE" in policy["dimensions"]["reproducibility_status"]["values"]


def test_verdict_taxonomy_forbids_a_generic_fail():
    policy = config.load("data_policy")
    tax = policy["verdict_taxonomy"]
    assert "FAIL_ACCESS_CONSTRAINT" in tax and "FAIL_DATA_UNAVAILABLE" in tax
    assert "generic FAIL is no longer an admissible" in tax["rule"]
    assert "NOT an epistemic finding" in tax["FAIL_ACCESS_CONSTRAINT"]


def test_gold_proxy_approved_with_a_mandatory_variance_sensitivity():
    """Monthly averaging is a low-pass filter and suppresses variance. Phase 6
    rests on second moments, so the effect must be quantified, not noted."""
    gold = config.load("data_policy")["approved_proxies"]["GOLD"]
    assert gold["approved"] is True
    sens = gold["mandatory_sensitivity"]
    assert sens["required"] is True
    assert "SUPPRESS" in sens["reason"]
    assert "never be labelled as LBMA-identical" in sens["must_not"]


def test_core_proxy_is_not_approved():
    assert config.load("data_policy")["approved_proxies"]["CORE"]["approved"] is False

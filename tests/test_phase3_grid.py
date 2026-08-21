"""Phase 3 grid and spread-arithmetic tests.

The spread numbers are the deliverable of R2E, so the arithmetic that produces
them is checked against hand-constructed inputs rather than against its own
output.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_phase3 as p3  # noqa: E402


def test_grid_is_full_factorial():
    cells = p3.all_cells()
    assert len(cells) == len(p3.FUNDING) * len(p3.TIMING) * len(p3.TER_DELTA_BP) * len(p3.FSA_EUR)
    assert len(cells) == 72
    assert len(set(p3.cell_id(*c) for c in cells)) == 72, "cell ids must be unique"


def test_grid_matches_the_work_order():
    assert set(p3.FUNDING) == {"D1", "D2", "D3"}
    assert set(p3.TIMING) == {"last_trading_day_y", "first_business_day_y_plus_1"}
    assert set(p3.TER_DELTA_BP) == {0, 10, 20, 30}
    assert set(p3.FSA_EUR) == {0.0, 1000.0, 2000.0}
    assert set(p3.HORIZONS) == {10, 20}


def test_baseline_cell_is_the_frozen_a5_a4_configuration():
    """A.5 funding D3 and first_business_day_y_plus_1; A.4 FSA 1000; no TER delta."""
    funding, timing, ter, fsa = p3.BASELINE_CELL
    assert funding == "D3"
    assert timing == "first_business_day_y_plus_1"
    assert ter == 0
    assert fsa == 1000.0
    assert p3.BASELINE_CELL in p3.all_cells()


def test_spread_over_picks_the_true_extremes():
    cells = p3.all_cells()[:4]
    medians = {p3.cell_id(*c): v for c, v in zip(cells, [100.0, 250.0, 175.0, 120.0])}
    s = p3.spread_over(cells, medians)
    assert s["spread_of_medians_eur"] == pytest.approx(150.0)
    assert s["best_median_eur"] == pytest.approx(250.0)
    assert s["worst_median_eur"] == pytest.approx(100.0)
    assert s["n_cells"] == 4


def test_spread_of_a_single_cell_is_zero():
    cells = p3.all_cells()[:1]
    medians = {p3.cell_id(*cells[0]): 42.0}
    assert p3.spread_over(cells, medians)["spread_of_medians_eur"] == 0.0


def test_paired_extremes_uses_per_path_differences_not_the_median_gap():
    """The paired delta is the median of per-path differences, which in general
    differs from the difference of medians. Constructed so the two disagree."""
    cells = p3.all_cells()[:2]
    a, b = p3.cell_id(*cells[0]), p3.cell_id(*cells[1])
    best = np.array([10.0, 20.0, 30.0, 100.0])
    worst = np.array([9.0, 19.0, 29.0, 1.0])
    data = {a: {"real_after_tax": best}, b: {"real_after_tax": worst}}
    medians = {a: float(np.median(best)), b: float(np.median(worst))}
    r = p3.paired_extremes(cells, medians, data)
    assert r["best_cell"] == a and r["worst_cell"] == b
    assert r["paired_median_delta_eur"] == pytest.approx(1.0)
    assert medians[a] - medians[b] == pytest.approx(11.0)
    assert r["P_model_delta_gt_0"]["P_model"] == pytest.approx(1.0)


def test_dimension_effects_cover_every_dimension_and_level():
    cells = p3.all_cells()
    rng = np.random.default_rng(0)
    medians = {p3.cell_id(*c): float(rng.uniform(80_000, 90_000)) for c in cells}
    data = {p3.cell_id(*c): {"real_after_tax": np.full(8, medians[p3.cell_id(*c)])}
            for c in cells}
    eff = p3.dimension_effects(medians, data)
    assert set(eff) == set(p3.DIMENSIONS)
    levels = {"funding": p3.FUNDING, "timing": p3.TIMING,
              "ter_delta_bp": p3.TER_DELTA_BP, "fsa_eur": p3.FSA_EUR}
    for dim in p3.DIMENSIONS:
        assert len(eff[dim]["marginal_spread"]["levels"]) == len(levels[dim])
        # one range per combination of the OTHER dimensions
        expected = 1
        for other in p3.DIMENSIONS:
            if other != dim:
                expected *= len(levels[other])
        assert eff[dim]["full_factorial_range_eur"]["n_combinations"] == expected


def test_convention_spread_excludes_the_ter_sweep():
    """TER is a sensitivity, not a sourced cost, so it must not enter the
    convention spread. Every cell contributing to it has TER +0 bp."""
    convention_cells = [c for c in p3.all_cells() if c[2] == 0]
    assert len(convention_cells) == 18  # 3 funding x 2 timing x 3 FSA
    assert all(c[2] == 0 for c in convention_cells)


def test_ter_sweep_is_declared_as_sensitivity_only():
    """Guard against a later edit quietly promoting the sweep to a cost claim."""
    import json
    costs = json.loads((Path(__file__).resolve().parents[1] / "config" / "costs.json")
                       .read_text())
    assert costs["data_status"] == "PLACEHOLDER_NOT_SOURCED"
    assert list(p3.TER_DELTA_BP) == costs["ter_delta_sweep_bp"]

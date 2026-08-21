"""The three-dimensional data status model (operator decision, 2026-08-21).

The earlier implementation collapsed availability, redistribution and
reproducibility into one licence_status, which produced the wrong inference
"not openly redistributable -> not available -> FAIL". These tests pin the
separation.
"""
import pytest

from portfolio_sim import data_registry as reg


def test_licensed_data_held_outside_the_repo_is_still_reproducible():
    """The central point: reproducibility != redistribution."""
    assert reg.classify_reproducibility("ACQUIRED", "RESTRICTED", True) == \
        "LICENSED_REPRODUCIBLE"


def test_open_acquired_and_hashed_is_open_reproducible():
    assert reg.classify_reproducibility("ACQUIRED", "OPEN", True) == "OPEN_REPRODUCIBLE"


def test_acquired_but_unhashed_is_not_reproducible():
    """Without a content hash a second party cannot establish byte equality."""
    assert reg.classify_reproducibility("ACQUIRED", "OPEN", False) == "NOT_REPRODUCIBLE"


@pytest.mark.parametrize("availability",
                         ["LICENCE_REQUIRED", "NOT_FOUND", "INSUFFICIENT_HISTORY"])
def test_unacquired_is_never_reproducible(availability):
    assert reg.classify_reproducibility(availability, "OPEN", True) == "NOT_REPRODUCIBLE"


def test_licence_status_maps_to_redistribution_not_to_availability():
    assert reg.redistribution_from_licence("LICENCE_REQUIRED") == "RESTRICTED"
    assert reg.redistribution_from_licence("OPEN") == "OPEN"
    assert reg.redistribution_from_licence("LICENCE_UNKNOWN") == "UNKNOWN"
    # A restricted licence says nothing about whether the data exists.
    assert "RESTRICTED" not in reg.AVAILABILITY


def test_the_three_vocabularies_are_distinct():
    assert not (set(reg.AVAILABILITY) & set(reg.REDISTRIBUTION))
    assert not (set(reg.REDISTRIBUTION) & set(reg.REPRODUCIBILITY))


def test_licensed_provenance_requires_a_hash_and_a_row_count():
    complete = {f: "x" for f in reg.LICENSED_PROVENANCE_FIELDS}
    ok, missing = reg.licensed_provenance_complete(complete)
    assert ok and not missing

    for dropped in ("sha256", "row_count", "acquisition_instructions"):
        partial = dict(complete)
        partial[dropped] = ""
        ok, missing = reg.licensed_provenance_complete(partial)
        assert not ok and dropped in missing


def test_source_status_triple_for_a_licensed_but_held_file():
    core = reg.SERIES_BY_KEY["CORE"]
    lseg = next(s for s in core.sources if "LSEG" in s.provider)
    triple = reg.source_status_triple(lseg, "ACQUIRED", local_file_hashed=True)
    assert triple == {
        "availability_status": "ACQUIRED",
        "redistribution_status": "RESTRICTED",
        "reproducibility_status": "LICENSED_REPRODUCIBLE",
    }


def test_core_as_it_stands_today_is_not_reproducible():
    """Nothing has been acquired, so whatever the licence says, no reproducible
    CORE input exists yet."""
    core = reg.SERIES_BY_KEY["CORE"]
    lseg = next(s for s in core.sources if "LSEG" in s.provider)
    triple = reg.source_status_triple(lseg, "LICENCE_REQUIRED", local_file_hashed=False)
    assert triple["reproducibility_status"] == "NOT_REPRODUCIBLE"
    assert triple["redistribution_status"] == "RESTRICTED"

# Licensed data provenance records

Metadata only — **never** the licensed bytes themselves. One JSON file per
series, named `<SERIES_KEY>.json`, carrying every field in
`data_registry.LICENSED_PROVENANCE_FIELDS`:

```
provider · series_or_index_identity · currency · return_convention
retrieval_date · licence_classification · original_filename · sha256
period_start · period_end · row_count · transformation_specification
acquisition_instructions
```

The raw file lives in `data/licensed/` (git-ignored). A second party holding the
same legitimate source recomputes the local hash and compares it against
`sha256` here. Equality establishes that both calibrated from identical bytes —
**licensed reproducibility**, weaker than open reproducibility and to be
labelled as such in every report.

A record missing any field does **not** count: `run_phase4.py` requires
`licensed_provenance_complete()` before it will issue `PASS_RESTRICTED_DATA`.
Directory currently empty by design — nothing has been acquired.

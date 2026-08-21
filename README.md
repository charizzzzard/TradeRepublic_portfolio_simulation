# Long-Term Portfolio Decision Simulation

Does a limited active satellite allocation, against a globally diversified
equity core, earn its added risk, tax, cost, concentration and complexity?

```
H0: 100 % global core remains the best non-falsified baseline.
H1: The satellite produces a material, robust portfolio effect that survives
    path, parameter and model uncertainty.
```

"No tested satellite delivers sufficiently robust incremental decision utility"
is a fully admissible — and expected — outcome. This is not a forecasting
system, and it does not derive an optimal portfolio from point forecasts.

## Status

| | |
|---|---|
| Baseline | `r0_baseline_20260821_v3` |
| Phases completed | **Phase 1 — `R2F_DECISION_PATH_CLEANUP`** (bootstrap variant)<br>**Phase 2 — `R11_SAVINGS_DYNAMICS`**<br>**Phase 3 — `R2E_CONVENTION_AND_COST_SENSITIVITY`**<br>Phase 4 — `R3_DATA_ACQUISITION` → `BLOCKED_NETWORK` |
| Governance status | `DISCOVERY` |
| `promotion_allowed` | `false` |
| Highest stage reachable today | `MODEL_CONSISTENT_FINDING` (Engine C only) |
| Human final decision | required |

Phases 5–7 have **not** run. Teil D forbids starting a phase whose predecessor
gate is not `PASS`, and that is now enforced in code (`src/portfolio_sim/gates.py`),
not merely documented.

**Frozen comparators.** Every admissible satellite finding must later be
reported against these:

| Comparator | 10 y | 20 y |
|---|---|---|
| `R11` — +1 pp contribution growth | 2,923 EUR (3.45 %) | **13,973 EUR (7.79 %)** |
| `R2E_CONVENTION_SPREAD` — funding × timing × FSA | 1,078 EUR (1.27 %) | 2,864 EUR (1.60 %) |
| `R2E_FULL_GRID_SPREAD` — incl. TER sensitivity sweep | 2,362 EUR (2.79 %) | 8,322 EUR (4.66 %) |

The savings lever dominates every convention and cost effect measured: at 20
years the entire 72-cell spread, *including* a hypothetical 30 bp TER penalty,
is 0.60× the value of one extra percentage point of contribution growth. A
30 bp TER difference alone (5,600 EUR) exceeds the 5,000 EUR G1 materiality
gate. See [`docs/PHASE2_R11.md`](docs/PHASE2_R11.md) and
[`docs/PHASE3_R2E.md`](docs/PHASE3_R2E.md).

## Read this before any number

Six limits govern every result. They are the *outcome* of the prior work, not
caution:

* **G1 — signal ≈ noise on expected values.** A 5,000 EUR materiality gate on a
  ~199,000 EUR median is a 0.124 pp/yr portfolio-CAGR difference, requiring a
  satellite excess of 0.83 pp/yr (15 % sleeve) to 2.48 pp/yr (5 % sleeve). The
  standard error of a return difference between two equity markets estimated
  from 50 years of history is 0.80–1.97 pp/yr. The requirement sits *inside* the
  error bar. Reproduce it with `python3 scripts/verify_g1.py`.
* **G2 — second moments are decidable.** Volatilities and correlations are
  estimable an order of magnitude more precisely than means. Only claims resting
  purely on second moments and tax/cost mechanics may pass a materiality gate.
* **G3 — rank stability is not a finding.** A rank ordering that echoes the input
  µ vectors is `ASSUMPTION_ECHO`, not evidence.
* **G4 — probabilities are model-conditional.** Every probability is written
  `P_model(...)` = `P(... | model, parameter prior)`. There is no probability
  statement about the real world.
* **G5 — effective n.** For parameter-level claims the effective n is the number
  of parameter worlds, not the number of paths. Both are annotated on every
  probability.
* **G6 — regimes are underdetermined.** Engine C is a scenario generator, not a
  probability generator. "In a persistent inflation world of type X, Y follows"
  is admissible; "X occurs with probability Z" is not.
* **G7 — convention dominance.** Terminal timing and funding convention move the
  real median by an amount comparable to the largest measured satellite
  advantage. While that holds, the satellite question is *subordinate* and must
  be reported as such.

## What this model does not include

Emergency fund, human capital, statutory and occupational pension, liquidity
events and interim withdrawals are **not modelled** (B.6). This is a partial
analysis of portfolio allocation, **not financial planning**.

FX is `EXCLUDED_BY_DESIGN` (B.5, `config/fx.json`). The EUR investor's unhedged
USD/JPY/EM exposure is out of scope, and no statement about a satellite's
currency risk is supported by this model.

All cost values are **unsourced placeholders**. All tax assumptions are
`TO_BE_VERIFIED`. Baseline v2 is absent from this repository — see
[`docs/BASELINE_V3.md`](docs/BASELINE_V3.md).

## Layout

```
config/       investor, conventions, tax, costs, fx, assets — data, hashed as data
src/          engine, tax engine, lot ledger, CRN, macro, metrics, manifest, ledger
tests/        hand checks + determinism + pre-tax regression + gates + grid (58 tests)
scripts/      run_phase1.py, run_phase2.py, run_phase3.py, verify_g1.py
results/      per-phase run_manifest.json, baseline reference, falsification ledger
docs/         BASELINE_V3.md, PHASE2_R11.md, PHASE3_R2E.md
```

## Run it

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -q      # 58 tests
python3 scripts/run_phase1.py    # acceptance checks + run_manifest.json
python3 scripts/run_phase2.py    # R11 savings dynamics (~5 min)
python3 scripts/run_phase3.py    # R2E convention/cost grid (~25 min)
python3 scripts/verify_g1.py     # recompute the G1 arithmetic
```

No result is valid without its `run_manifest.json` (Teil C).

## Governance ladder

```
DISCOVERY → CALIBRATED_DISCOVERY → MODEL_CONSISTENT_FINDING
          → EMPIRICAL_SUPPORT → POLICY_CANDIDATE → HUMAN_DECISION
```

No stage may be skipped, and `MODEL_CONSISTENT_FINDING ≠ EMPIRICAL_SUPPORT ≠
POLICY`. Engine B/C can never award more than `MODEL_CONSISTENT_FINDING`; only
Engine A, on real historical data, can award `EMPIRICAL_SUPPORT`. Both rules are
enforced in code (`src/portfolio_sim/manifest.py`), not merely documented.

## Phase 4 is blocked, not failed

`R3_DATA_ACQUISITION` ran and returned **`BLOCKED_NETWORK`**: this environment
has no egress to any host, confirmed against canary hosts that are not data
sources. That is a fact about the container, not a finding about the data, so no
`PASS`/`PARTIAL`/`FAIL` was issued — `FAIL` would mean "CORE is not obtainable",
which nothing here evidences. The separation is enforced in code, not by
convention. See [`docs/PHASE4_R3.md`](docs/PHASE4_R3.md).

An external browsing assistant has since answered the data request
(`data/external/findings_20260821.json`, hashed and referenced from the Phase 4
manifest). It reports CORE and GOLD as `LICENCE_REQUIRED`, HICP and €STR as open,
and supplied all ten TERs with issuer KID dates. **Acceptance is unchanged**: the
findings are recorded as `EXTERNALLY_REPORTED` with `verified_locally: false`,
because nothing was downloaded, counted or hashed here — and because the CORE
question was asked about MSCI ACWI when `IE00BK5BQT80` actually tracks **FTSE
All-World**. That registry defect is fixed; the decisive question is now open and
unanswered. A second round then answered the CORE question for the correct index: FTSE
All-World long history is a licensed LSEG product (public Historic Index Values
give ~2 years), and the Vanguard NAV fallback has only ~7 years. Candidate
verdict, recorded but **not issued**: `FAIL_PENDING_LOCAL_VERIFICATION`.

Round 2 also found a **second** registry error of mine — `IE00BK5BQT80`
benchmarks **FTSE All-World NR USD**, not EUR — which puts the B.5 decision
`fx: EXCLUDED_BY_DESIGN` in conflict with calibration and must be resolved by the
operator before any calibrated run. Recorded as
`SPECIFICATION_CONFLICTS["B5_FX_VS_USD_BENCHMARK"]`, status `OPEN`.

**No empirical data is loaded.** Every result in this repository still rests on
an `UNCALIBRATED_ASSUMPTION` prior, and `EMPIRICAL_SUPPORT` remains unreachable.

## Next phase

Two options, and the choice is the operator's:

**Re-run Phase 4 with network access.** The only path to `CALIBRATED_DISCOVERY`
or `EMPIRICAL_SUPPORT`. `python3 scripts/run_phase4.py` in an environment with
egress will acquire what it can and classify the rest with source-level outcomes
that *are* admissible as findings.

**Or proceed to Phase 5 (`R6_NULL_TESTS`) on the uncalibrated prior.** The null
tests and the µ-neutral gold claim are constructed to need no empirical µ, and
their ceiling is `MODEL_CONSISTENT_FINDING` either way. But `gates.require_phase_pass`
refuses any phase whose predecessor acceptance is not `PASS`, so this requires an
explicit decision to override — `BLOCKED_NETWORK` is not `PARTIAL`, and the code
will not treat it as such on its own.

Phase 5 would isolate how much of any measured satellite advantage is pure
rebalancing mechanics with no return assumption at all
(`REBALANCING_REFERENCE_SCALE`), and Null C1 (`delta == 0` exactly) is a
STOP-level implementation check.

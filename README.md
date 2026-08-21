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
| Phases completed | **Phase 1 — `R2F_DECISION_PATH_CLEANUP`** (bootstrap variant)<br>**Phase 2 — `R11_SAVINGS_DYNAMICS`** |
| Governance status | `DISCOVERY` |
| `promotion_allowed` | `false` |
| Highest stage reachable today | `MODEL_CONSISTENT_FINDING` (Engine C only) |
| Human final decision | required |

Phases 3–7 have **not** run. Teil D forbids starting a phase whose predecessor
gate is not `PASS`, and that is now enforced in code (`src/portfolio_sim/gates.py`),
not merely documented.

**Frozen R11 comparator** — every admissible satellite finding must later be
reported against it: +1 pp contribution growth is worth a paired median
**2,923 EUR (3.45 % of core median) at 10 years** and **13,973 EUR (7.79 %) at
20 years**, both with `P_model(delta > 0) = 100 %`. See
[`docs/PHASE2_R11.md`](docs/PHASE2_R11.md).

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
tests/        28 hand checks + determinism + pre-tax regression + gates (49 tests)
scripts/      run_phase1.py, run_phase2.py, verify_g1.py
results/      per-phase run_manifest.json, baseline reference, falsification ledger
docs/         BASELINE_V3.md, PHASE2_R11.md
```

## Run it

```bash
pip install -r requirements.txt
python3 -m pytest tests/ -q      # 49 tests
python3 scripts/run_phase1.py    # acceptance checks + run_manifest.json
python3 scripts/run_phase2.py    # R11 savings dynamics (~5 min)
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

## Next phase

**Phase 3 — `R2E_CONVENTION_AND_COST_SENSITIVITY`**: cross-tabulate funding
convention (D1/D2/D3), terminal timing, TER delta (0/10/20/30 bp) and FSA
(0/1000/2000 EUR) on 100 % CORE, on shared worlds under CRN. If the largest
convention spread meets or exceeds the best satellite median delta, the
`CONVENTION_DOMINANCE_CONFIRMED` flag fires and the satellite question is
reported as subordinate (G7).

Note that TER must be *swept*, not read from `config/costs.json`: every value
there is an unsourced placeholder, and a 0.20 pp TER delta alone exceeds the
0.124 pp G1 materiality gate.

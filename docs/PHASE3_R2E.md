# Phase 3 — `R2E_CONVENTION_AND_COST_SENSITIVITY`

Acceptance **PASS** (7/7). Governance `DISCOVERY`, `promotion_allowed: false`.

Full factorial on 100 % CORE: 3 funding × 2 terminal timings × 4 TER deltas ×
3 FSA levels = **72 cells per horizon**, horizons 10 and 20, 40 parameter worlds
× 500 paths = 20,000 paired paths per cell. Every cell within a horizon shares
the same worlds and the same `CRNBlock` instance, so all 72 are paired path by
path.

Baseline cell = the A.5/A.4 frozen configuration:
`D3 | first_business_day_y_plus_1 | ter+0bp | fsa1000`.

## Marginal spread of the real median terminal value, ranked

**20 years** (baseline cell median 178,647 EUR):

| Dimension | Marginal spread | % of baseline | Full-factorial max range | Paired median Δ (best vs worst) | `P_model(Δ>0)` |
|---|---|---|---|---|---|
| TER delta | **5,600 EUR** | 3.13 % | 5,696 | 5,585 | 1.000 |
| FSA | 2,794 EUR | 1.56 % | 2,815 | 2,651 | 1.000 |
| Funding | 124 EUR | 0.07 % | 825 | 63 | 0.667 |
| Terminal timing | 41 EUR | 0.02 % | 166 | 10 | 0.678 |

**10 years** (baseline cell median 84,537 EUR):

| Dimension | Marginal spread | % of baseline | Full-factorial max range | Paired median Δ | `P_model(Δ>0)` |
|---|---|---|---|---|---|
| TER delta | **1,316 EUR** | 1.56 % | 1,349 | 1,337 | 1.000 |
| FSA | 1,077 EUR | 1.27 % | 1,077 | 960 | 1.000 |
| Terminal timing | 77 EUR | 0.09 % | 109 | 4 | 0.628 |
| Funding | 0 EUR | 0.00 % | 88 | 0 | 0.000 |

## Frozen comparators

Hash `98db26185b8e854a…` (`results/phase3/frozen_comparators.json`).

| Comparator | 10 y | 20 y |
|---|---|---|
| `R2E_CONVENTION_SPREAD` (funding × timing × FSA, TER pinned at +0 bp) | 1,078 EUR (1.27 %) | **2,864 EUR (1.60 %)** |
| `R2E_FULL_GRID_SPREAD` (all 72 cells, includes the TER sweep) | 2,362 EUR (2.79 %) | **8,322 EUR (4.66 %)** |

The two are reported separately on purpose. Funding convention, terminal timing
and FSA are real, knowable circumstances. The TER sweep is a *sensitivity*, not
a sourced cost difference — `config/costs.json` is still
`PLACEHOLDER_NOT_SOURCED` — so a spread that includes it is a hypothetical band,
not a measured cost of choosing wrongly.

## Against the frozen R11 comparator

Recomputed on Phase 3's exact 40 worlds so the comparison is paired rather than
across differing world sets. It reproduces the Phase 2 value frozen on 100
worlds to **0.2 % (10 y)** and **0.03 % (20 y)** — the comparator is stable
under a 2.5× change in world count.

| | 10 y | 20 y |
|---|---|---|
| R11, +1 pp contribution growth | 2,917 EUR | 13,969 EUR |
| Convention spread ÷ R11 | 0.37× | **0.21×** |
| Full-grid spread ÷ R11 | 0.81× | **0.60×** |

**The savings lever dominates everything measured in this phase.** At 20 years
the entire 72-cell spread — including a hypothetical 30 bp TER penalty — is
0.60× the value of one extra percentage point of contribution growth. The
convention spread proper is 0.21×.

Ordering at 20 years:

```
+1 pp savings   13,969  >  TER 30bp  5,600  >  FSA 0->2000  2,794  >  funding 124  >  timing 41
```

## Four findings worth stating plainly

**1. TER is the dominant cost lever, and it clears the G1 gate on its own.**
A 30 bp TER difference costs 5,600 EUR of real terminal wealth over 20 years,
which **exceeds the 5,000 EUR G1 materiality gate**. The levels are near-linear
at roughly 1,867 EUR per 10 bp (178,647 → 176,773 → 174,883 → 173,046), so the
break-even against the gate falls at about **27 bp**. This confirms B.4's
rationale empirically rather than by assertion: an unsourced 20–30 bp TER
uncertainty is not a detail, it is the whole materiality budget. Until
`config/costs.json` carries sourced values, no cost-sensitive claim can be
promoted.

**2. Spread-of-medians badly overstates the paired effect for the small
dimensions.** Terminal timing shows a 77 EUR marginal spread at 10 years, but
the paired median difference between the best and worst timing cell is **4 EUR**,
with `P_model(Δ>0) = 0.628` — barely better than a coin flip on sign. Funding at
20 years: 124 EUR spread, 63 EUR paired, `P_model = 0.667`. PROJECT_META asks
for the spread of medians, so that is what is frozen, but reporting it alone
would make two effects look ~15× larger and far more reliable than they are.
Both are reported.

**3. Funding convention is inert while the FSA is intact.** At 10 years the
marginal spread across D1/D2/D3 is **exactly zero**: with the statutory 1,000 EUR
allowance absorbing the Vorabpauschale, there is no tax to fund during
accumulation, so the three conventions never diverge. The effect appears only in
the FSA = 0 corner (full-factorial max range 825 EUR at 20 years). Funding
convention is not a free-standing risk; it is conditional on the allowance
already being consumed elsewhere.

**4. The FSA effect is strongly asymmetric.** Going 0 → 1,000 EUR is worth
2,012 EUR at 20 years; 1,000 → 2,000 EUR only 782 EUR. With 500 EUR/month from a
13,000 EUR base, the taxable Vorabpauschale rarely exceeds the single-filer
allowance until late in the horizon, so the second allowance is mostly idle.

## A discrepancy against the v2 figures in PROJECT_META

G7 cites terminal timing moving the real median by ~222 EUR and funding D1 vs D4
by up to ~554 EUR. On baseline v3 the marginal timing effect is **41–77 EUR** and
the marginal funding effect **0–124 EUR** — roughly an order of magnitude
smaller for timing.

This is reported as an observation, not a correction. The v2 package is absent
from this repository, so the difference cannot be diagnosed: it could be a
different FSA assumption, different parameters, or a different definition of the
spread. Note also that **D4 is not reproducible at all** — A.5 defines only
D1/D2/D3, so the "D1 vs D4" spread has no counterpart in v3 and was not
attempted.

What this means for G7: the *left-hand side* of the convention-dominance
inequality is now measured on v3 and frozen. It is materially smaller than the
v2 figures the G7 narrative was built on.

## What was NOT done

**No satellite was simulated and no satellite-vs-convention comparison was
made.** `CONVENTION_DOMINANCE_CONFIRMED` is defined against the best satellite
median delta, which does not exist on baseline v3:

```json
"convention_dominance": {
  "flag": "NOT_EVALUABLE",
  "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
  "legacy_v2_comparator_allowed": false
}
```

The v2 satellite figures quoted in PROJECT_META are not admissible as the
comparator. The flag becomes evaluable only when a phase produces a valid v3
satellite delta.

## Reproducibility

* Phase 2 predecessor gate enforced in code: `acceptance == PASS`,
  `parameter_hash` unchanged, all convention-bearing modules byte-identical to
  HEAD. No engine or baseline convention was modified.
* Determinism `PASS_EXACT`: two identical full runs, bit-identical across all
  **432 arrays** (72 cells × 3 metrics × 2 horizons), and
  `convention_cost_sensitivity.json` byte-identical across both.
* The R11 recomputation is deterministic and agrees with the frozen Phase 2
  value.

## Standing caveats

Costs remain unsourced placeholders — which findings 1 and the frozen
`R2E_FULL_GRID_SPREAD` now show is the single most consequential open item in
the cost model. All tax assumptions remain `TO_BE_VERIFIED`. FX is
`EXCLUDED_BY_DESIGN`. B.6 boundary conditions are unmodelled. Phase 3 produces
no ranking of assets (G3), and every probability is `P_model` with effective
n = 40 parameter worlds (G5).

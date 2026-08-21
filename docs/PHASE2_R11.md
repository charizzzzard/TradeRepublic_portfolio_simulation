# Phase 2 — `R11_SAVINGS_DYNAMICS`

Acceptance **PASS**. Governance status `DISCOVERY`, `promotion_allowed: false`.

100 % CORE only. 100 parameter worlds × 500 paths = 50,000 paired paths per
cell; 2 horizons × 4 growth rates = 8 cells. Within a horizon all four growth
scenarios share the same parameter worlds and the **same `CRNBlock` instance**,
so every delta is paired path by path — the pairing is structural, not a
convention someone has to remember.

## The frozen R11 comparator

Paired real terminal wealth delta, **3 % minus 2 %** contribution growth
(= exactly +1 pp), after tax, 100 % CORE:

| Horizon | Median delta | As % of core median terminal | `P_model(delta > 0)` |
|---|---|---|---|
| 10 years | 2,923 EUR | 3.45 % | 100.0 % |
| 20 years | 13,973 EUR | 7.79 % | 100.0 % |

`n_parameter_worlds = 100`, `n_paths_per_world = 500`. Effective n for
parameter-level claims is **100**, not 50,000 (G5).

This value is **frozen**. Every admissible satellite finding must later be
reported against it.

## Levels

Real terminal value after tax, median (full percentiles in
`results/phase2/savings_dynamics.json`):

| Growth | 10 years | 20 years |
|---|---|---|
| 0 % | 79,363 EUR | 155,509 EUR |
| 2 % | 84,800 EUR | 179,312 EUR |
| 3 % | 87,726 EUR | 193,522 EUR |
| 5 % | 94,099 EUR | 226,695 EUR |

## Two things the numbers say that the levels alone do not

**The money-weighted return is almost flat across growth rates** — 4.67 % →
4.68 % at 10 years, 4.82 % → 4.84 % at 20 years. Contribution growth does not
change the *rate of return*; it changes the *amount exposed to it*. This is
precisely why Phase 2 forbids a CAGR on DCA cashflows: a start-to-end CAGR
would move with the contribution schedule and invite the reading that saving
more "earns more per euro", which it does not.

**`P_model(real terminal < real contributions)` rises slightly with growth** —
29.04 % → 29.24 % (10 y) and 22.42 % → 23.11 % (20 y). Money contributed later
has less time to compound, so a steeper schedule shifts weight toward
contributions with shorter exposure. The effect is small but it is the right
sign, and it is a reminder that the growth lever is not free of sequence risk.

## What was NOT done, and why

PROJECT_META Phase 2 requires the comparison

> Effekt +1 pp Sparratendynamik **vs.** größtes gemessenes Satelliten-Median-Delta

**This comparison was not performed.** No satellite has been simulated on
baseline v3, and the satellite figures quoted in PROJECT_META were produced by
the v2 package, which is absent from this repository. Comparing a v3 measurement
against a v2 figure that cannot be reproduced here would manufacture a result
out of an unverifiable input. Recorded in the manifest as:

```json
"satellite_comparison": {
  "required": true,
  "status": "DEFERRED_PENDING_VALID_V3_SATELLITE_DELTA",
  "legacy_v2_comparator_allowed": false,
  "r11_comparator_frozen": true
}
```

Phase 2 is complete as R11 on its own terms. The cross-phase comparison becomes
an explicit gate condition on whichever phase first produces a valid v3
satellite delta.

## One comparison that IS admissible now

Distinct from the deferred satellite comparison: the Phase 6 GOLD **wealth
gate**, pre-registered in `results/falsification_ledger.json` before any run,
requires a median delta of **≥ 3.0 % of the core median terminal value**.

The +1 pp savings lever is **7.79 %** of the core median at 20 years — roughly
2.6× that entire materiality threshold — and it clears it with
`P_model(delta > 0) = 100 %`, whereas the gate only asks a satellite for 60 %.

This compares a measurement against a *frozen threshold*, not against an
unmeasured satellite, so it is not circular. It does not decide anything about
gold. What it does establish is the order of magnitude the satellite question is
competing against, which is the point of running R11 first.

## Reproducibility

* Predecessor gate enforced in code: `gates.require_phase_pass` refuses to run
  unless Phase 1's manifest records `acceptance == PASS`, `parameter_hash` is
  unchanged, and every convention-bearing module is byte-identical to the
  pinned baseline `5efb528`. Verified, all PASS.
* Determinism: two identical full runs, bit-identical across all 56 arrays, and
  `savings_dynamics.json` byte-identical across both.
* `xirr_monthly` was called with `iters=80` instead of the library default 200.
  Verified **bit-identical** to the default at runtime and recorded as an
  acceptance check; `metrics.py` is unmodified (`iters` is an existing
  parameter). This is a performance choice with no numerical consequence.
* Dependencies are now pinned exactly (`numpy==2.4.6`, `pytest==9.1.1`, plus
  `constraints.txt`). `environment_hash` identifies drift after the fact; the
  pins are what prevent it.

## Standing caveats

All cost values remain unsourced placeholders and all tax assumptions remain
`TO_BE_VERIFIED`. FX is `EXCLUDED_BY_DESIGN`. B.6 boundary conditions —
emergency fund, human capital, pensions, liquidity events, interim withdrawals —
are not modelled, and the contribution schedule modelled here assumes the
investor can actually sustain the growth rate, which is exactly the kind of
constraint B.6 excludes. Phase 2 produces no ranking of assets (G3).

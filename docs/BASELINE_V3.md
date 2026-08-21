# Baseline v3 — technical record

`baseline_id: r0_baseline_20260821_v3`

## Why there is a v3 at all

PROJECT_META A.5 freezes a baseline v2:

```
package_sha256:  f88d542fbc48ec4ff99c688b6158ed48c1ca0916dc0e9f5c8c313aad4e2d0d71
tax_engine.py:   ffd89ab2fdf45b7e8b35f8025dd537552df29ecfe10b30874716817cd8c9a59c
```

**Neither artefact exists in this repository.** The repository had zero commits
when this work began. Those hashes therefore cannot be reproduced, and Phase 1's
stated acceptance criterion — `Vorsteuer-Regression PASS_EXACT` against v2 — is
unsatisfiable by construction.

Reporting a `PASS` against a baseline reconstructed from the same document that
describes it would be exactly the DATA / MODEL-ASSUMPTION confusion Teil E
exists to prevent. So it was not done. Instead:

* v2 is recorded in `config/conventions.json` under `supersedes` with
  `status: UNREPRODUCIBLE_IN_REPO`;
* v3 is declared as a fresh, self-hashed baseline;
* the *invariant* the v2 regression was protecting is checked directly
  (see "Pre-tax regression" below).

**Consequence for reading results.** Every quantitative figure quoted in
PROJECT_META — the ~199,000 EUR median terminal value, the ~222 EUR terminal-timing
spread, the ~554 EUR D1-vs-D4 funding spread, the G3 rank ordering — originates
from v2 and has **not** been reproduced here. Comparing a v3 number against any
of them is not a validated regression.

## Frozen conventions carried over from A.5

| Item | Value |
|---|---|
| seed | 20260815 |
| return convention | `exp(log1p(g)/12 + vol/sqrt(12)*z)`, no Itō correction |
| funding convention | D3 `reduce_next_contribution` |
| terminal sale timing | `first_business_day_y_plus_1` |
| FSA cap tolerance | 1e-8 EUR |
| CRN | mandatory |

The return convention makes `g` the **median** annual log growth, not the
arithmetic mean; the simulated mean exceeds `g` by roughly σ²/2. This is the
frozen convention and is deliberately not "corrected" (`HC19`).

## Decisions taken in this phase

**B.5 — FX.** `option_b: EXCLUDED_BY_DESIGN`, decided by the human operator and
recorded in `config/fx.json`. No FX process is modelled; asset processes are
read as EUR total returns with the currency component folded into their
volatility. The EUR investor's unhedged USD/JPY/EM exposure is out of scope and
**no statement about a satellite's currency risk is supported by this model**.
B.5 requires this disclosure to be restated in every result report.

**B.1 — withholding tax credit.** Marked `NOT_IN_DECISION_PATH`. The branch is
retained, tested (`HC22`, `HC23`) and *corrected*: §32d applies the credit
against the 25 % Einkommensteuer with the Solidaritätszuschlag applied
afterwards — `e = (K − 4q)/(4 + k)` — whereas the v2 defect credited against
26.375 % directly. On K = 1000, q = 50 that is 211.00 EUR, not 213.75 EUR.
This correction is **not** a decision-path claim: no gate may depend on it
(`HC24`), and it is unreachable because no instrument in the universe is
`direct_stocks`.

**B.2 — Basiszins.** Coupled to the modelled short rate with a floor at 0, which
itself reverts to a target that moves with modelled inflation. A high-inflation
path therefore cannot carry a zero Basiszins. Over the reference run the mean
Basiszins is ≈ 2.1 % with ≈ 12 % of years at the floor, consistent with the
historical reference in `config/tax.json` (2021/2022 → 0, 2023–2025 ≈ 2.3–2.6 %).
`legal_status: TO_BE_VERIFIED` against the annual BMF-Schreiben.

**B.3 — Gold.** Both variants are configured and both carry
`legal_status: TO_BE_VERIFIED`; `b3_dual_reporting.required = true` makes a
single-variant GOLD result an invalid deliverable. Under both variants an ETC is
a debt security, so no Vorabpauschale applies (`HC07`).

**B.4 — Costs.** `config/costs.json` exists as its own parameter class. **Every
value in it is an unsourced placeholder** (`data_status: PLACEHOLDER_NOT_SOURCED`).
Since a 0.20 pp TER delta alone exceeds the 0.124 pp G1 gate, Phase 3 must treat
TER as a *swept dimension* (0/10/20/30 bp) rather than reading these point values,
and no cost-sensitive claim may be promoted until they are sourced.

## Bugs found and fixed while building the acceptance suite

1. **Church-tax rate treated as a percentage** in the §32d denominator
   (`4 + k`), where the statute uses a decimal fraction. Gave 8.8 % instead of
   27.9951 %. Caught by `HC02`/`HC03`.

2. **Vorabpauschale charged against the wrong tax year's allowance.** The engine
   reset the FSA *after* accruing the Vorabpauschale. But the Vorabpauschale for
   year Y accrues on the first working day of year Y+1, so it belongs to tax
   year Y+1 and must share **one** Sparer-Pauschbetrag with anything else
   realised in Y+1. The original ordering granted a second allowance — and under
   `first_business_day_y_plus_1` it handed the terminal disposal its own fresh
   1000 EUR. Fixed by resetting before accruing (`HC26`, `HC27`).

3. **Lot ledger under-allocated.** Rebalancing adds a lot per asset per year
   boundary, which the preallocation did not budget for.

4. **Singular correlation matrices were perturbed.** `np.linalg.cholesky`
   rejects a perfectly-correlated (PSD but rank-deficient) matrix, and the
   fallback clipped eigenvalues to 1e-10 and renormalised. Two perfectly
   correlated assets then drifted apart, triggering spurious rebalancing trades
   and ~1.15 EUR of avoidable tax. The exact-PSD case now uses the symmetric
   eigen square root with no perturbation.

5. **CRN was not actually common across portfolios.** Each portfolio factored
   its own correlation sub-matrix, so a shared asset's correlated shock depended
   on which *other* assets were in the portfolio — the guarantee held only for
   the first asset in the ordering, and paired comparisons were quietly not
   paired. The correlation matrix is now factored over the **full canonical
   universe** and columns are sliced, so each asset's shock is a fixed function
   of the shared draws.

Items 4 and 5 mattered enough to be worth stating plainly: without them, a
future Phase 5 Null C1 test (`delta == 0` exactly) or Phase 6 paired comparison
would have carried mechanical noise of the same order as the effects it is
meant to measure.

## Pre-tax regression

Baseline v2 is absent, so no regression against it was run. What is checked
instead — and what the v2 regression was actually protecting — is the invariant
that **the tax configuration must not perturb the pre-tax mechanics**. Under
funding convention D2 tax is paid from outside the portfolio, so the pre-tax
path must be bit-identical across FSA settings, church-tax rates,
Teilfreistellung, Basiszins slope, GOLD tax variant and terminal timing. All
checked at bit equality in `tests/test_pretax_regression.py`.

## Reference run

40 parameter worlds × 250 paths, 20 years, 100 % CORE, baseline conventions.
The parameter prior is `UNCALIBRATED_ASSUMPTION`: Phase 4 (R3) has not run, no
empirical data exists, and **no claim rests on these numbers**. They exist to
pin the baseline hash so later phases have something to regress against.

Phase 1 produces **no ranking of assets** (G3).

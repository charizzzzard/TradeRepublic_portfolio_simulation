# Operator decisions, 2026-08-21

Three decisions taken after Phase 4 round 2. All three tighten the framework
rather than relax it: each replaces a coarse rule with a distinction the
evidence forced.

---

## Decision 1 — B.5 resolved without a separate FX process

**`option_b` retained, redefined as `EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR`.**

The error was never the absence of a simulated FX factor. It was the clause
saying non-EUR asset returns are *"interpreted"* as EUR returns with the FX
component *"folded into their volatility"*. For FTSE All-World NR **USD** that
sentence is simply false — reading USD returns as EUR returns omits FX rather
than absorbing it.

| | |
|---|---|
| **Historical calibration** | Every non-EUR benchmark series **MUST** be converted to EUR *before* return estimation. `I_EUR(t) = I_FOREIGN(t) × FX(t)`, quote convention documented per series. |
| **Simulation** | Simulate the resulting EUR-denominated process. No separate FX factor, no modelled FX/asset correlation. |
| **Supported** | EUR-investor total-return behaviour |
| **Unsupported** | isolated FX risk · FX hedging decisions · FX forecasts · asset-vs-currency decomposition |

This is **data preprocessing, not a stochastic process**, so option_b's original
motivation survives intact: no future USD/EUR correlation has to be
parameterised, and the parameter space does not expand into a dimension G6-style
underdetermination would make unestimable. What changes is that calibration now
measures the risk a EUR investor actually bears instead of a USD investor's risk
relabelled.

### Phases 1–3: demonstrated unaffected, not assumed

`config/fx.json` is read by no numeric code path, and Phases 1–3 load no
historical series. Rather than assert this, the repository now **proves** it:

* `hashing.py` splits `parameter_hash` (everything) from
  `numeric_parameter_hash` (configs that can move a number — deliberately
  conservative, including `investor.json` and `assets.json` even though the
  engine does not currently read them).
* `gates.require_phase_pass` fails **hard** on numeric drift, and records
  documentary drift as visible-but-non-invalidating.
* `tests/test_config_separation.py` **mutates `fx.json` and `data_policy.json`
  on disk, re-runs the simulation, and requires bit equality.** If that
  exemption were ever wrong, the test fails.
* Phases 1–3 were then re-run end to end and every frozen comparator hash
  compared against its pre-revision value.

A manifest written before the split records no numeric hash; the gate then falls
back to the full hash, which is the *stricter* comparison — never a skip.

---

## Decision 2 — licensed data and proxies

### A. Licensed data outside the repository is admissible

The requirement "raw data must be redistributable from this public repository"
is retired as a precondition for reproducibility. It conflated two things:

```
reproducibility != redistribution
```

Three properties are now tracked independently
(`config/data_policy.json`, `data_registry.py`):

| Dimension | Values |
|---|---|
| `availability_status` | `ACQUIRED` · `LICENCE_REQUIRED` · `NOT_FOUND` · `INSUFFICIENT_HISTORY` · … |
| `redistribution_status` | `OPEN` · `RESTRICTED` · `UNKNOWN` |
| `reproducibility_status` | `OPEN_REPRODUCIBLE` · `LICENSED_REPRODUCIBLE` · `NOT_REPRODUCIBLE` |

Licensed raw files live in `data/licensed/` (git-ignored, never committed). The
repository carries the provenance and an expected SHA-256; a second party
holding the same legitimate source recomputes the hash and compares. Equality
establishes that both calibrated from identical bytes.

That is **licensed reproducibility** — weaker than open reproducibility, and it
must be labelled as such in every report. It is not irreproducibility.

### B. Proxies — selectively

**GOLD: approved.** World Bank Pink Sheet, monthly since 1960, CC BY 4.0,
institutional primary provider, redistribution permitted with attribution.

With a **mandatory sensitivity attached**, not merely a note: the target is the
LBMA PM **month-end** fixing; the proxy is the **monthly average** of daily
fixings. Averaging is a low-pass filter and will **suppress measured variance**.
Phase 6 rests entirely on second moments (G2), so a gold downside claim
calibrated on averaged data would understate precisely the quantity the claim is
about. The variance reduction must be quantified as its own proxy sensitivity
before any calibrated Phase 6 result is reported, and the series must never be
labelled LBMA-identical.

**CORE: not approved.** Vanguard NAV starts 2019-07-23 (`INSUFFICIENT_HISTORY`,
and a fund series rather than the benchmark); Kenneth French is not FTSE
All-World, is USD, lacks a net-of-withholding concept, and inherits
MSCI/Bloomberg licence constraints. **CORE remains the binding constraint.**

---

## Decision 3 — `LICENCE_REQUIRED` is not automatically a Teil D `FAIL`

The old chain — *not openly redistributable → not available → FAIL* — was too
coarse. It turned a statement about this project's access rights into a claim
about the world's data. **A generic `FAIL` is no longer an admissible Phase 4
verdict.**

| Verdict | Meaning |
|---|---|
| `FAIL_DATA_UNAVAILABLE` | `NOT_FOUND`, `DATA_INVALID` or `INSUFFICIENT_HISTORY`. **Epistemic**: the series does not exist in usable form. |
| `FAIL_ACCESS_CONSTRAINT` | `LICENCE_REQUIRED` and the licence/file not obtained. **Not epistemic**: `data_exists: true`, `data_acquired: false`. Still a STOP for calibrated phases. |
| `BLOCKED_NETWORK` | Environment-level. No egress. Not a research finding of any kind. |

### The CORE decision rule

```
exact CORE acquired openly              → PASS,                  OPEN_REPRODUCIBLE
exact CORE licensed, outside repo,
  hashed, provenance complete           → PASS,                  LICENSED_REPRODUCIBLE
exact CORE commercial, no licence/file  → FAIL_ACCESS_CONSTRAINT, NOT_REPRODUCIBLE
operator-approved proxy in use          → PARTIAL, PROXY_CALIBRATION
                                          (EMPIRICAL_SUPPORT ceiling reconsidered)
otherwise                               → FAIL_DATA_UNAVAILABLE, NOT_REPRODUCIBLE
```

So the expected post-egress verdict is no longer a bare `FAIL` but:

```
FAIL_ACCESS_CONSTRAINT
  series:               CORE
  provider:             FTSE Russell / LSEG
  data_exists:          true
  data_acquired:        false
  redistribution:       restricted
  calibration_possible: false
```

A STOP for calibrated phases — but not the claim that the series does not exist.

---

## Also fixed: a circularity in Phase 1's own acceptance

`run_phase1.py` ran the full test suite as an acceptance check, and the suite
contains tests asserting on `run_phase1`'s own manifest. A single failure
therefore became **self-perpetuating**: the manifest recorded `FAIL`, which made
the gate tests fail, which kept the manifest at `FAIL`.

Tests that assert on a phase's own output are now marked `@pytest.mark.phase_artifact`
and excluded from that phase's acceptance run. A phase cannot validate itself
with a test that reads its own result — that was never meaningful validation,
only a deadlock waiting to happen.

---

## What is still open

The B.5 resolution is recorded but **has not been exercised**: no non-EUR series
has been converted to EUR, because no series has been acquired at all. The FX
quote convention will need to be recorded per series at that point, and a
quote-direction error is not detectable from the numbers alone — it silently
inverts the currency effect.

Governance remains `DISCOVERY`, `promotion_allowed: false`.

# Phase 4 — `R3_DATA_ACQUISITION`

**Acceptance: `BLOCKED_NETWORK`.** All six procedural checks pass. Governance
stays `DISCOVERY`, `promotion_allowed: false`.

`BLOCKED_NETWORK` **is not `FAIL`.** `FAIL` is a finding about the world —
"CORE is not obtainable" — and Teil D makes it a STOP condition. This run
produced no such finding, because it produced no evidence about any source. It
established a fact about this container.

## The evidence for the block

Egress was probed against **canary hosts that are not data sources**
(`example.com`, `iana.org`) before any source was contacted. That ordering is
the point: had we probed MSCI first and got a refusal, we could not have told a
licence wall from a firewall.

| Channel | Result |
|---|---|
| `curl` via `HTTPS_PROXY` | `CONNECT tunnel failed, response 403` — every host |
| `curl --noproxy '*'` | HTTP 403 |
| `WebFetch` tool | `{"error_type":"EGRESS_BLOCKED"}` |
| DNS | resolves only via a wildcard proxy domain (`…ax4z.com`) |
| Proxy `recentRelayFailures` | `connect_rejected … gateway answered 403 to CONNECT (policy denial)` for every host |

`example.com` failing is what makes this conclusive: the denial is uniform and
policy-level, not source-specific. 19 source fetches across 14 series, plus 10
TER document fetches — **0 acquired**, all classified `NETWORK_BLOCKED`.

## How the distinction is enforced

Not by convention, but structurally, in `src/portfolio_sim/data_acquisition.py`:

* Outcomes are split into two **disjoint** vocabularies — environment-level
  (`NETWORK_BLOCKED`, `NETWORK_TIMEOUT`, `NETWORK_DNS_FAILURE`) and source-level
  (`ACQUIRED`, `SOURCE_NOT_FOUND`, `LICENCE_OR_AUTH_REQUIRED`, `DATA_INVALID`).
* `classify()` collapses **every** result to `NETWORK_BLOCKED` when the canary
  probe failed — even a 404, which would otherwise look like a genuine finding
  about a source. With no egress, a 404 carries no information.
* `research_verdict_admissible()` is the single gate the runner must consult
  before writing any `PASS`/`PARTIAL`/`FAIL`. It returns `False` here, so no
  verdict was issued.

Tested directly, including the adversarial case where a raw attempt returns a
source-shaped outcome under a blocked probe.

## What was built, and is ready to run

**`src/portfolio_sim/data_registry.py`** — the authoritative specification of
all 14 required series (10 assets + 4 macro), each with provider, priority tier,
endpoint, licence status, currency, frequency, return convention and the exact
transformation required. Plus PRIIPs KID / factsheet sources for all 10
instruments' TER.

Every URL is marked **`endpoint_status: UNVERIFIED`**. These are intended
endpoints recorded from specification; none has been confirmed to resolve,
because nothing here can reach the network. A test enforces that the registry
says so rather than implying validation that did not happen.

Licence position as specified: **10 `OPEN`, 7 `LICENCE_REQUIRED`, 2
`LICENCE_UNKNOWN`**. The `LICENCE_REQUIRED` set is concentrated exactly where
PROJECT_META predicted — MSCI (CORE, EM, DIVIDEND), S&P, STOXX/Deutsche Börse,
Bloomberg.

**`data_manifest.csv`** carries every provenance column PROJECT_META requires
(source, retrieval date, frequency, currency, return convention, start/end,
SHA256, transformations, licence status). For all 19 rows the period,
observation-count and hash fields are **empty**. An empty field is honest; a
placeholder would be fabricated provenance.

## Findings that did not need the network

**Effective sample size — the mandatory statistical note.** From ~50 years of
history, 20-year rolling windows give:

| Count | Value |
|---|---|
| Overlapping monthly windows | **361** |
| Independent increments `(T−h)/h` | **1.5** |
| Non-overlapping windows `⌊T/h⌋` | 2 |

PROJECT_META's "~1.5 independent observations" corresponds to `(T−h)/h`. The
gap between 361 and 1.5 is a factor of **240**. Any P10/P90 computed from those
361 windows would look like a distribution over hundreds of observations while
resting on about one and a half. That is why the reporting rule forbids
presenting them as a distribution, and it is now computed rather than quoted.

**CORE has no clean open substitute.** The academic fallback (Kenneth French
Data Library) covers *developed* markets and therefore is **not ACWI** — it
excludes emerging markets entirely. It is registered as a candidate proxy with
an explicit requirement for a documented splice rule and its own `data_status`,
and a test asserts that flag is present so it cannot quietly stand in for CORE.
This is the shape of the real blocker: the free sources are not the index, and
the index is licensed.

## Cost / TER sourcing: attempted, not achieved

All 10 PRIIPs KID / factsheet fetches were blocked. **`config/costs.json` is
unchanged and remains `PLACEHOLDER_NOT_SOURCED`.**

I could have written plausible TER values from model training. I did not, and
the reason is not caution but definition: such values would carry no source URL,
no retrieval date and no content hash. They would be indistinguishable in
substance from the placeholders already there while being *dressed* as sourced —
which is precisely the fabricated-provenance failure PROJECT_META forbids, and
worse than an honest placeholder because it removes the flag that says "do not
rely on this".

Phase 3 sharpened why this matters: a 30 bp TER difference costs 5,600 EUR of
real terminal wealth over 20 years, **exceeding the 5,000 EUR G1 materiality
gate on its own**. Sourcing these values is a precondition for any
cost-sensitive claim.

Note also that **tracking difference is not disclosed in a KID**. It must be
derived from fund NAV history against the licensed index series — which is the
same licence blocker as CORE.

## Governance

Unchanged: `DISCOVERY`, `promotion_allowed: false`. `CALIBRATED_DISCOVERY`
requires calibration against acquired data, which did not happen. No stage was
skipped and none was awarded on the strength of a blocked run.

`gates.require_phase_pass` refuses any phase whose predecessor acceptance is not
`PASS`, so **Phase 5 is blocked by default and this run does not lift that.**

Whether to proceed to Phases 5/6 on the `UNCALIBRATED_ASSUMPTION` prior is an
operator decision, not one this run may make. PROJECT_META's `PARTIAL` branch
contemplates them running with the remaining satellites left
`INDETERMINATE_BY_CONSTRUCTION` — but `BLOCKED_NETWORK` is not `PARTIAL`.
Analytically, the null tests (Phase 5) and the µ-neutral gold claim (Phase 6)
are constructed to need no empirical µ, and their ceiling is
`MODEL_CONSISTENT_FINDING` either way. What R3 blocks unconditionally is
`EMPIRICAL_SUPPORT`, which only Engine A on real data can award.

## To complete R3

Re-run `python3 scripts/run_phase4.py` in an environment with egress. It will
probe, acquire what it can, and classify the rest with source-level outcomes
that *are* admissible as findings. Expected first tasks there:

1. Promote or correct the `UNVERIFIED` endpoints.
2. Establish whether an EUR net-total-return ACWI history is obtainable, and on
   what licence terms. This decides `PASS` vs `PARTIAL` vs `FAIL`.
3. Read the 10 PRIIPs KIDs and replace the TER placeholders.
4. Validate the modelled Basiszins against the published BMF values via the
   Bundesbank Umlaufrendite series — the step that would move B.2 from
   `TO_BE_VERIFIED` to `VERIFIED`.

---

# Addendum — external findings, 2026-08-21

An external browsing assistant answered the data request. Its report is recorded
verbatim at `data/external/findings_20260821.json` (hashed, and referenced from
the Phase 4 manifest).

**Acceptance is unchanged: `BLOCKED_NETWORK`. Phase 5 remains gated.** The
findings are recorded as `EXTERNALLY_REPORTED` evidence with
`verified_locally: false`. They are not a verdict, for two independent reasons
given below.

## What was reported

| Series | Reported status | Substance |
|---|---|---|
| CORE | `LICENCE_REQUIRED` | No ≥360-month MSCI ACWI NR EUR raw series verifiable for redistribution; MSCI forbids reproduction without prior written consent |
| GOLD | `LICENCE_REQUIRED` | LBMA moved historical prices into MyLBMA; access needs an IBA licence, otherwise ICE purchase |
| HICP_EA | `ACQUIRED_OPEN` | **Our series key was dead.** `ICP.M.U2.N.000000.4.ANR` discontinued 2026-02-04, replaced by `HICP.M.U2.N.000000.4D0.ANR` |
| SHORT_RATE_EA | `ACQUIRED_OPEN` | Bundesbank `BBMMB.M.EU000A2X2A25.WT`, native from 2019-10 |
| BUND_LONG_YIELD | `NOT_FOUND` | Legacy `BBK01.WT3230` not mappable to the current database; a candidate exists, equivalence unproven |
| TER | 10/10 reported | Ongoing charges with issuer KID URLs and document dates |

Question B answered: **no admissible open proxy for CORE.** Kenneth French is
developed-markets only, USD not EUR, no MSCI-style net-of-withholding concept,
no explicit open-redistribution licence — and its international portfolios use
MSCI data to 2006 and Bloomberg after, so the licence problem is inherited
rather than avoided.

## Why this is not yet a verdict

**1. Nothing here was verified.** No file was downloaded, no row counted, no
hash computed — correctly, since the reporter declined to transcribe 300+ rows
by hand. Teil D's `CORE-Daten nicht verfügbar → STOP` is a finding about the
world and needs evidence this run can reproduce. Recording a `FAIL` on
second-hand testimony would be the same category error as recording one on a
network timeout.

**2. The question was asked about the wrong index — my error.** `IE00BK5BQT80`
is the **Vanguard FTSE All-World UCITS ETF (Acc)**, which tracks **FTSE
All-World**. This registry specified the CORE calibration series as **MSCI
ACWI**. Those are different indices with different constituent methodologies.
So the reported MSCI `LICENCE_REQUIRED` does not settle CORE — it settles a
series the study does not simulate. FTSE All-World has not been assessed at all.

That defect is now fixed: `data_registry.py` targets FTSE All-World as the tier-1
CORE source, retains the MSCI finding explicitly labelled as concerning a
different index, and a test asserts the identity.

## Corrections applied to the registry

* **CORE** target changed from MSCI ACWI to **FTSE All-World** (tier 1,
  `LICENCE_UNKNOWN` — the open question).
* **GOLD** LBMA source updated to the MyLBMA/IBA position, `OPEN` →
  `LICENCE_REQUIRED`. The old open JSON endpoint is marked superseded.
* **HICP_EA** migrated to `HICP.M.U2.N.000000.4D0.ANR`; a test fails if the
  discontinued key reappears.
* **SHORT_RATE_EA** switched to the Bundesbank native monthly series, with the
  **EONIA splice rule written into the transformation**: EONIA ran under its own
  methodology to 2019-09-30, then was mechanically €STR + 8.5 bp until
  2022-01-03. A test asserts the rule is present and marked never-silent.
* **BUND_LONG_YIELD** records the candidate `BBSIS…` series but blocks mapping
  it until the yield concept behind `WT3230` is established.
* **French Data Library** downgraded `OPEN` → `LICENCE_UNKNOWN` and its
  rejection reasons recorded.

## TER: reported, deliberately not adopted

All ten values arrived with issuer KID URLs and document dates — real provenance,
much better than the invented placeholders. **`config/costs.json` is still
unchanged.** Two reasons, and neither is squeamishness:

1. I cannot open or hash those KIDs. Writing the values in would claim a
   verification that did not occur.
2. **Adopting them invalidates Phases 1–3.** `parameter_hash` is part of every
   gate; changing base TER changes the drag in every simulated path, so the
   frozen `R2E_CONVENTION_SPREAD` and `R2E_FULL_GRID_SPREAD` — and the R11
   comparator — would all have to be recomputed. That is a deliberate decision
   with a real cost, not a side effect of a config edit.

Worth noting how large the correction would be: reported CORE TER is **0.14 %**
against the **0.20 %** placeholder. Phase 3 measured ~1,867 EUR per 10 bp over
20 years, so that single 6 bp difference is worth roughly **1,100 EUR** of real
terminal wealth — about 22 % of the G1 materiality gate, from one instrument's
placeholder being wrong.

## Candidate verdict, recorded but not issued

`FAIL_OR_PARTIAL_PENDING_VERIFICATION`. If the reported licence positions hold
*and* also hold for FTSE All-World, no redistributable CORE calibration series
exists and Teil D forces `FAIL`/STOP. If an FTSE All-World EUR net-total-return
history proves obtainable, `PASS` or `PARTIAL` becomes reachable. Both branches
are open.

One distinction to carry into whichever verdict is finally issued:
**`LICENCE_REQUIRED` is not `does not exist`.** The data exists and is
obtainable commercially. What is unavailable is a version this repository may
redistribute. A `FAIL` on those grounds is a statement about this project's
open-reproducibility constraint, not about the data's existence.

---

# Addendum 2 — external findings round 2, 2026-08-21

Recorded at `data/external/findings_round2_20260821.json` (hashed, ingested by
`run_phase4.py`). **Acceptance is still `BLOCKED_NETWORK`; Phase 5 is still
gated.** But the candidate verdict has firmed from
`FAIL_OR_PARTIAL_PENDING_VERIFICATION` to **`FAIL_PENDING_LOCAL_VERIFICATION`**.

## CORE — the question is now materially answered

Round 1 asked about the wrong index. Round 2 asked about **FTSE All-World**, the
actual benchmark, and answered it:

* LSEG's freely accessible **Historic Index Values give roughly two years** of
  month-end values. Longer history is a licensed subscription product, and LSEG
  requires a licence for use *and distribution* of index data.
* The Vanguard NAV fallback is **`INSUFFICIENT_HISTORY`**: share class inception
  **2019-07-23**, so ~7 years exist against the 360 required — and fund NAV is
  net of fees and tracking difference, so it is not the benchmark series anyway.

No ≥360-month CORE series is redistributable under this project's
open-reproducibility condition.

## A second specification error — also mine

`IE00BK5BQT80`'s official benchmark is **FTSE All-World NR USD**. The fund's base
currency is USD; **EUR is a listing/trading currency only.** My registry had
recorded EUR, inferred from the fact that the ETF trades in EUR.

So the registry was wrong twice about the same series: first the index, then the
currency. Both are now corrected, and a test asserts `currency == "USD"`.

## The consequence neither dossier drew: B.5 is now in conflict

This is the most decision-relevant thing to come out of round 2, and it reaches
beyond Phase 4.

`config/fx.json` records B.5 as `option_b: EXCLUDED_BY_DESIGN`, with the
rationale that asset processes are *"interpreted as EUR-denominated total returns
with the FX component folded into their volatility"*. That rationale is only
true for a natively EUR-denominated series. **The CORE benchmark is USD.**

Calibrating CORE from a USD series leaves two options, and both break the
recorded rationale:

1. **Convert USD → EUR with an FX series.** That *is* an FX process — precisely
   what `option_b` excludes.
2. **Treat USD returns as EUR returns.** That does not "fold FX into volatility";
   it **omits FX entirely**, misstating both the mean and the variance faced by a
   EUR investor.

**Scope:** Phases 1–3 are *not* invalidated — they run on an assumed prior, not
on calibrated data, and the conflict bites only at calibration. But B.5 must be
revisited **before any calibrated run**, and the rationale text in
`config/fx.json` is inaccurate as written once a USD benchmark is in play.

Recorded as `SPECIFICATION_CONFLICTS["B5_FX_VS_USD_BENCHMARK"]`, status `OPEN`,
`decision_owner: human operator` — it is a Teil B first-class assumption, not an
implementation detail, so `config/fx.json` was **not** changed unilaterally.
Three resolution options are recorded there.

## GOLD — an admissible open proxy now exists

Unlike the CORE situation, this one has a real answer. **World Bank Pink Sheet**,
monthly since 1960, **CC BY 4.0**, redistribution permitted with attribution,
from an institutional primary provider.

But it is *not* a silent substitute: the target is the **LBMA PM month-end**
fixing; the proxy is the **monthly average of daily London afternoon fixings**.
Averaging suppresses month-end volatility — which matters directly for a claim
resting on second moments (G2). Registered with the difference stated and a
requirement for a documented substitution rule and its own `data_status`.

## `WT3230` — a specification error, not a rename

Round 2 is sharper than round 1: the official Bundesbank migration catalogue
contains **no entry** for `BBK01.WT3230`. The candidate series is documented as
the successor of **`WU9555` / `WU0115`**, not of `WT3230`. So the key I recorded
was almost certainly invented rather than superseded.

Mapping stays blocked. The same Bundesbank table also carries maturity-band
series (3–5, 5–8, 8–15, 15–30 years), and which is correct depends on the
Basiszins *concept* — the very thing B.2 lists as `TO_BE_VERIFIED`.

## TER — still not adopted, and round 2 shows why

Round 2 found that **at least two round-1 document dates were wrong** (COMMOD is
2026-06-16, not 2026-04-09; NASDAQ differs too), and that **KID versions are
locale- and jurisdiction-dependent**. Provenance must therefore carry
`isin, provider, locale, document_date, source_url, sha256, retrieval_date` —
not just ISIN and URL.

That is a direct vindication of hashing before adoption: two of ten dates moved
between rounds, from the same reporter, within a day.

## What would settle the verdict

A single run with egress that fetches the LSEG Historic Index Values page and the
FTSE All-World licence terms *itself* and records the observed coverage. That is
cheap — **it does not require obtaining the data, only confirming it is not
obtainable openly.**

And the distinction to carry into the verdict: `LICENCE_REQUIRED` is not "the
data does not exist". It exists and is commercially obtainable. What does not
exist is a version this repository may redistribute. A `FAIL` here is a statement
about a condition **this project imposed on itself**.

If that condition were relaxed — licensed data held outside the repo, or a
documented open proxy with its own `data_status` — `PARTIAL` becomes reachable:
GOLD now has an admissible open proxy, HICP and €STR are open. **CORE is the
binding constraint either way.**

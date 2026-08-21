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

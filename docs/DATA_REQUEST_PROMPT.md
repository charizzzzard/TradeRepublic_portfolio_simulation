# Data request prompt for an LLM with internet access

Copy everything below the line into an assistant that can browse. Return its
output to this session (or drop the files into `data/incoming/`).

---

You are procuring **primary/official historical financial data**. Accuracy of
provenance matters more than completeness — a documented "not available" is a
useful answer; a plausible-looking substitute is a harmful one.

## Hard rules

1. **Only primary or official sources**, in this priority order: official index
   provider → central bank → Destatis/Eurostat → academic dataset (Kenneth
   French, Shiller) → high-quality institutional provider.
2. **Never silently substitute a different index.** If MSCI ACWI is not
   obtainable, do not return MSCI World, FTSE All-World, or an ETF's NAV history
   as if it were ACWI. Return it *labelled as a proxy*, with the difference
   stated (e.g. "developed markets only, excludes EM").
3. **Never estimate, interpolate, or recall numbers from memory.** Every number
   must come from a URL you actually opened in this session.
4. If a series is licence-encumbered, say so and state the terms. Also state
   whether **redistribution in a public git repository** is permitted — this
   matters as much as whether the data can be downloaded.
5. Report failures explicitly as `LICENCE_REQUIRED`, `NOT_FOUND`,
   `REGISTRATION_REQUIRED`, or `PAYWALLED`.

## What is needed, in priority order

| # | Series | Specification |
|---|---|---|
| 1 | **CORE** *(critical)* | MSCI ACWI **Net Total Return, EUR, monthly**, ≥ 360 months. This one decides the whole phase. |
| 2 | **GOLD** | LBMA gold PM auction price, monthly month-end, USD or EUR, longest available |
| 3 | **HICP_EA** | Euro-area HICP all-items, monthly, annual rate of change (ECB SDW `ICP.M.U2.N.000000.4.ANR`) |
| 4 | **BUND_LONG_YIELD** | Bundesbank Umlaufrendite / long-dated Bund yield, monthly (`BBK01.WT3230`) |
| 5 | **SHORT_RATE_EA** | Euro short-term rate (€STR), monthly; note the EONIA splice date if used |
| 6 | **TER** | Ongoing charges from the **PRIIPs KID or official factsheet** for each ISIN below |

ISINs for #6: `IE00BK5BQT80` (CORE), `IE00B5BMR087` (SP500), `IE00B53SZB19`
(NASDAQ), `IE00BK5BR626` (DIVIDEND), `LU0328475792` (EUROPE), `DE0005933931`
(DAX), `IE00B4L5YX21` (JAPAN), `IE00BKM4GZ66` (EM), `IE00B4ND3602` (GOLD),
`IE00BDFL4P12` (COMMOD).

For each: confirm the ISIN maps to the fund you think it does, give the exact
ongoing-charges figure, the KID document URL, and its document date.

## Two specific questions I need answered

**A.** Is an EUR net-total-return MSCI ACWI monthly history obtainable *at all*
without a commercial licence? If not, say so plainly — that is the finding.

**B.** If not, what is the best **openly licensed** global equity total-return
monthly series in EUR, and precisely how does it differ from ACWI (index
coverage, net vs gross of withholding tax, currency treatment)?

## Output format

For each series, one block:

```
series_key:        CORE
status:            ACQUIRED | LICENCE_REQUIRED | NOT_FOUND | REGISTRATION_REQUIRED | PAYWALLED
is_proxy:          yes/no   (if yes: what it is, and how it differs from the target)
source_provider:
source_url:        (the exact URL you downloaded from)
retrieval_date:    (UTC)
frequency:         monthly
currency:
return_convention: total_return_net | total_return_gross | price_only | rate
period_start:      YYYY-MM
period_end:        YYYY-MM
n_observations:
licence_status:    OPEN | LICENCE_REQUIRED | LICENCE_UNKNOWN
redistribution_in_public_repo: permitted / not permitted / unclear
transformations:   (any transformation you applied; "none" if raw)
```

Then the data as **CSV with a header**, `date,value`, ISO dates, `.` decimal
separator, no thousands separators.

**Prefer giving me a direct download URL over transcribing a long series.**
If you transcribe 360+ rows by hand you will introduce errors, and I cannot
verify them against the source. A working URL plus the first and last five rows
is more useful than a full transcription. If you can compute the SHA-256 of the
downloaded file, include it.

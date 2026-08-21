# Data request prompt — round 2

Round 1 (2026-08-21) is recorded at `data/external/findings_20260821.json`. It
established licence positions but could not settle CORE, because the question
was asked about the wrong index. This round fixes that and asks for verifiable
artefacts.

Copy everything below the line into an assistant that can browse.

---

You are procuring **primary/official historical financial data**. A documented
"not available" is a useful answer; a plausible-looking substitute is a harmful
one. Never estimate or recall numbers from memory — every number must come from
a URL you opened in this session.

## Question 1 — the decisive one

`IE00BK5BQT80` is the **Vanguard FTSE All-World UCITS ETF (Acc)**. It tracks the
**FTSE All-World Index**, *not* MSCI ACWI. A previous round confirmed MSCI ACWI
is licence-encumbered, but that is the wrong index for this study.

**Is a FTSE All-World Net Total Return, EUR, monthly history (≥ 360 months)
obtainable — and may it be redistributed in a public git repository?**

Check FTSE Russell / LSEG directly, and also whether Vanguard itself publishes
a long monthly NAV or benchmark-return history for this fund. State the licence
and redistribution terms explicitly, not just whether a download exists.

If it is not obtainable openly, say so plainly. That is the finding, and it
settles the phase.

## Question 2 — files I can hash

For the two series already confirmed open, I need **verifiable artefacts**, not
descriptions. For each, give the direct download URL, then either attach the
file or paste the complete CSV, plus its SHA-256 if you can compute one, plus
the exact row count and first/last three rows.

* **HICP_EA** — `https://data-api.ecb.europa.eu/service/data/HICP/M.U2.N.000000.4D0.ANR?format=csvdata`
* **SHORT_RATE_EA** — `https://api.statistiken.bundesbank.de/rest/data/BBMMB/M.EU000A2X2A25.WT?format=csv&lang=de`

If the Bundesbank MIME type (`application/vnd.bbk.data+csv`) will not render in
your interface, try `format=sdmx` or the CSV download from the series' web page
instead, and say which worked.

## Question 3 — one factual clarification

The Bundesbank key `BBK01.WT3230` no longer resolves. Which **current** series
is its correct successor, and what yield concept did `WT3230` actually
represent — Umlaufsrendite of all domestic bearer bonds, of listed federal
securities, or something else? I will not map the candidate
`BBSIS.M.I.UMR.RD.EUR.S1311.B.A604.A.R.A.A._Z._Z.A` until this is answered,
because the Basiszins coupling depends on the concept, not the label.

## Question 4 — gold, openly

LBMA now gates historical prices behind an IBA licence. Is there **any** openly
redistributable long monthly gold price series — Bundesbank, World Gold Council,
FRED, or a central bank? If not, say so; gold then stays `LICENCE_REQUIRED`.

## Question 5 — the KID PDFs

Round 1 reported ongoing charges for all ten ISINs. I could not open those
documents. Please give the **direct PDF URL** for each, and if possible the
file's SHA-256, so the value can be tied to a document I can verify later.

ISINs: `IE00BK5BQT80`, `IE00B5BMR087`, `IE00B53SZB19`, `IE00BK5BR626`,
`LU0328475792`, `DE0005933931`, `IE00B4L5YX21`, `IE00BKM4GZ66`, `IE00B4ND3602`,
`IE00BDFL4P12`.

## Output

Per item: `status` (`ACQUIRED` / `LICENCE_REQUIRED` / `NOT_FOUND` /
`REGISTRATION_REQUIRED` / `PAYWALLED`), `source_url`, `retrieval_date`,
`licence_status`, `redistribution_in_public_repo`, and — where data was actually
downloaded — `period_start`, `period_end`, `n_observations`, `sha256`, and the
CSV itself.

Do not transcribe long series by hand. A working URL with a row count and the
first and last three rows beats an error-prone full transcription.

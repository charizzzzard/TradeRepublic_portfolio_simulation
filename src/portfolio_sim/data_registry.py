"""Authoritative registry of the historical series R3 must acquire.

This module contains NO DATA. It specifies, per series, which primary or
official source is authoritative, what transformation is required, and what the
licence position is. Keeping the specification separate from the acquisition
means the requirement is reviewable and hashable even when acquisition cannot
run.

Source priority (PROJECT_META Phase 4):

    1 official index provider
    2 central bank
    3 Destatis / Eurostat
    4 academic dataset
    5 high-quality institutional provider

IMPORTANT - endpoint verification status
----------------------------------------
Every `url` below is an INTENDED endpoint recorded from specification, not an
endpoint this repository has confirmed resolves. Nothing in this environment can
reach the network, so no URL here has been validated. Each entry therefore
carries `endpoint_status: UNVERIFIED`, and the first task of any run with real
network access is to promote or correct these.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

REQUIRED_COMMON_MONTHS = 360  # 30 years of overlapping coverage


DATA_ARTIFACT = "DATA_ARTIFACT"
EVIDENCE = "EVIDENCE"

# How the source relates to the series it is filed under. EVIDENCE about a
# DIFFERENT_INDEX or a PROXY can never establish a fact about the EXACT series.
EXACT = "EXACT"
PROXY = "PROXY"
DIFFERENT_INDEX = "DIFFERENT_INDEX"
SERIES_RELATIONS = (EXACT, PROXY, DIFFERENT_INDEX)

# What proposition the evidence is supposed to establish. Naming it makes the
# verdict rule checkable: FAIL_ACCESS_CONSTRAINT needs a COVERAGE_LIMIT AND a
# LICENCE_REQUIREMENT, both EXACT - not merely "some page returned 200".
COVERAGE_LIMIT = "COVERAGE_LIMIT"
LICENCE_REQUIREMENT = "LICENCE_REQUIREMENT"
PRODUCT_IDENTITY_EVIDENCE = "PRODUCT_IDENTITY"
INSUFFICIENT_HISTORY_EVIDENCE = "INSUFFICIENT_HISTORY"
EVIDENCE_KINDS = (COVERAGE_LIMIT, LICENCE_REQUIREMENT, PRODUCT_IDENTITY_EVIDENCE,
                  INSUFFICIENT_HISTORY_EVIDENCE)


@dataclass(frozen=True)
class SourceSpec:
    """One candidate source for one series.

    `role` is the distinction that stops an HTTP 200 from being read as an
    acquisition:

      DATA_ARTIFACT  a downloadable series file. Only this role, and only when
                     it parses to at least one observation, can make a series
                     ACQUIRED.
      EVIDENCE       a page documenting availability, coverage or licence terms.
                     Fetching it successfully establishes what the terms ARE -
                     never that the data was obtained.
    """
    provider: str
    tier: int
    url: str
    licence_status: str          # OPEN | LICENCE_REQUIRED | LICENCE_UNKNOWN
    endpoint_status: str = "UNVERIFIED"
    note: str = ""
    role: str = DATA_ARTIFACT
    evidence_purpose: str = ""
    # Machine-readable evidence semantics. A human-readable evidence_purpose is
    # not checkable; these are.
    series_relation: str = EXACT
    evidence_kind: str = ""
    validator_id: str = ""
    # Prepared for the calibration parsers, which are NOT built yet. A
    # DATA_ARTIFACT without a parser_id can never yield DATA_ACQUIRED.
    parser_id: str = ""


@dataclass(frozen=True)
class SeriesSpec:
    """One required time series."""
    key: str
    description: str
    required_for: str            # which phase/claim depends on it
    frequency: str
    currency: str
    return_convention: str       # total_return | price_only | rate | index_level
    transformation: str
    sources: tuple[SourceSpec, ...]
    blocker: str = ""

    def as_dict(self) -> dict:
        d = asdict(self)
        d["sources"] = [asdict(s) for s in self.sources]
        return d


# --------------------------------------------------------------------------
# Equity and commodity series
# --------------------------------------------------------------------------
SERIES: tuple[SeriesSpec, ...] = (
    SeriesSpec(
        key="CORE",
        description="Global all-country equity net total return - the benchmark the whole "
                    "study is defined against. The tracked index is FTSE All-World "
                    "NET RETURN, denominated in USD. IE00BK5BQT80 is the Vanguard FTSE "
                    "All-World UCITS ETF (Acc); its base currency is USD and EUR is a "
                    "listing/trading currency only. Two earlier versions of this registry "
                    "were wrong: first the index (MSCI ACWI, a different index), then the "
                    "currency (NR EUR, asserted merely because the ETF trades in EUR).",
        required_for="PHASE_5, PHASE_6, and every calibrated statement. CORE missing "
                     "is the one condition that forces STOP.",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="FTSE All-World NR USD -> monthly log returns, then an EXPLICIT "
                       "USD->EUR conversion for the EUR investor, per B.5 "
                       "(EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR): the conversion is "
                       "MANDATORY data preprocessing and the FX quote convention must be "
                       "recorded with the series. See config/fx.json.",
        sources=(
            SourceSpec("FTSE Russell / LSEG (historic index values)", 1,
                       "https://www.lseg.com/en/ftse-russell/index-resources/"
                       "historic-index-values", "LICENCE_REQUIRED",
                       role=EVIDENCE, series_relation=EXACT,
                       evidence_kind=COVERAGE_LIMIT,
                       validator_id="lseg_coverage_limit",
                       evidence_purpose="availability_and_coverage: documents that the "
                                        "freely accessible history is about two years of "
                                        "month-end values, far short of the 360 required",
                       note="THE CORRECT TARGET INDEX. Externally reported 2026-08-21 "
                            "(round 2): LSEG's freely accessible Historic Index Values "
                            "typically give only about TWO YEARS of month-end values; "
                            "longer history is a licensed subscription product and LSEG "
                            "requires a licence for use and distribution. A >=360-month "
                            "redistributable series could NOT be verified."),
            SourceSpec("FTSE Russell / LSEG (licence terms)", 1,
                       "https://www.lseg.com/en/ftse-russell/index-resources",
                       "LICENCE_REQUIRED",
                       role=EVIDENCE, series_relation=EXACT,
                       evidence_kind=LICENCE_REQUIREMENT,
                       validator_id="lseg_licence_requirement",
                       evidence_purpose="licence_terms: documents that use and "
                                        "distribution of LSEG index data require a "
                                        "licence, and that longer history is a "
                                        "subscription product",
                       note="Fetching this page successfully establishes the LICENCE "
                            "position. It does NOT obtain any data and must never "
                            "contribute to acquisition."),
            SourceSpec("Vanguard (fund NAV)", 5,
                       "https://www.vanguard.co.uk/professional/product/etf/equity/9679/"
                       "ftse-all-world-ucits-etf-usd-accumulating", "LICENCE_UNKNOWN",
                       role=EVIDENCE, series_relation=PROXY,
                       evidence_kind=INSUFFICIENT_HISTORY_EVIDENCE,
                       evidence_purpose="availability: documents share class inception "
                                        "2019-07-23, establishing INSUFFICIENT_HISTORY "
                                        "for the FUND series. Relation is PROXY: the fund "
                                        "NAV is not the benchmark, so this can never "
                                        "establish an access constraint on the benchmark.",
                       note="INSUFFICIENT_HISTORY and a proxy in any case. Share class "
                            "inception 2019-07-23, so at most ~7 years exist against the "
                            "360 required. Fund NAV is also net of fund fees and tracking "
                            "difference, so it is not the benchmark series."),
            SourceSpec("MSCI", 1, "https://www.msci.com/end-of-day-data-search",
                       "LICENCE_REQUIRED", role=EVIDENCE,
                       series_relation=DIFFERENT_INDEX,
                       evidence_kind=LICENCE_REQUIREMENT,
                       evidence_purpose="licence_terms for MSCI ACWI, a DIFFERENT index. "
                                        "Retained for the record; must never contribute "
                                        "to a verdict about FTSE All-World.",
                       note="MSCI ACWI - NOT the index the CORE instrument tracks. "
                            "Retained only because round 1 assessed it. Reported "
                            "LICENCE_REQUIRED; does not settle CORE."),
            SourceSpec("Kenneth R. French Data Library (Dartmouth)", 4,
                       "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
                       "Developed_3_Factors_CSV.zip", "LICENCE_UNKNOWN",
                       series_relation=PROXY,
                       note="CANDIDATE PROXY ONLY - REJECTED. NOT ACWI and not FTSE "
                            "All-World: developed markets only, USD not EUR, no "
                            "net-of-withholding-tax concept, no explicit "
                            "open-redistribution licence, and its international portfolios "
                            "use MSCI raw data to 2006 and Bloomberg thereafter, so the "
                            "licence problem is inherited rather than avoided. Would "
                            "require an explicit SPLICE rule and its own data_status."),
        ),
        blocker="CONFIRMED LICENCE_REQUIRED for the correct index. FTSE All-World long "
                "history is a licensed LSEG product and is not redistributable in a public "
                "repository. The data exists commercially; what is unavailable is a "
                "version this project may redistribute.",
    ),
    SeriesSpec(
        key="GOLD",
        description="Gold spot price, the only satellite with a testable claim (Phase 6).",
        required_for="PHASE_6 gold downside claim",
        frequency="monthly", currency="EUR", return_convention="price_only",
        transformation="LBMA PM auction price, month-end; EUR series or USD with a "
                       "documented FX treatment (currently out of scope per B.5)",
        sources=(
            SourceSpec("LBMA / ICE Benchmark Administration", 1,
                       "https://www.lbma.org.uk/prices-and-data/lbma-precious-metal-prices",
                       "LICENCE_REQUIRED", role=EVIDENCE, series_relation=EXACT,
                       evidence_kind=LICENCE_REQUIREMENT,
                       evidence_purpose="licence_terms: documents that historical prices "
                                        "moved into MyLBMA and require an IBA licence",
                       note="Externally reported 2026-08-21: LBMA moved historical tabular "
                            "precious-metal prices into the MyLBMA portal; access requires "
                            "an IBA licence, otherwise LBMA directs users to purchase from "
                            "ICE. The former open JSON endpoint "
                            "(prices.lbma.org.uk/json/gold_pm.json) is superseded."),
            SourceSpec("World Bank (Pink Sheet)", 5,
                       "https://thedocs.worldbank.org/en/doc/"
                       "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
                       "CMO-Historical-Data-Monthly.xlsx", "OPEN",
                       series_relation=PROXY,
                       note="ADMISSIBLE OPEN PROXY CANDIDATE, CC BY 4.0, redistribution "
                            "permitted with attribution. Monthly from 1960. Definition: "
                            "Gold (UK), 99.5% fine, London afternoon fixing, AVERAGE OF "
                            "DAILY RATES. DIFFERS FROM TARGET: the target is the LBMA PM "
                            "MONTH-END fixing; averaging suppresses month-end volatility, "
                            "which matters directly for a claim resting on second moments "
                            "(G2). Requires a documented substitution rule and its own "
                            "data_status before use - it may not stand in silently."),
            SourceSpec("Deutsche Bundesbank", 2,
                       "https://api.statistiken.bundesbank.de/rest/download/BBEX3/"
                       "D.USD.EUR.BB.AC.000", "OPEN",
                       note="For the EUR/USD leg if a USD gold series is used."),
        ),
    ),
    SeriesSpec(
        key="SP500", description="US large cap total return.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1 - not required for any "
                     "tested claim",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="total return index -> monthly log returns",
        sources=(
            SourceSpec("S&P Dow Jones Indices", 1, "https://www.spglobal.com/spdji/",
                       "LICENCE_REQUIRED", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="licence_terms",
                       note="Total return history is a licensed product."),
            SourceSpec("Robert Shiller (Yale) online data", 4,
                       "http://www.econ.yale.edu/~shiller/data/ie_data.xls", "OPEN",
                       note="Monthly S&P with dividends since 1871; academic dataset."),
        ),
    ),
    SeriesSpec(
        key="NASDAQ", description="US technology-heavy large cap.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="USD", return_convention="price_only",
        transformation="index level -> monthly log returns",
        sources=(SourceSpec("Nasdaq", 1, "https://www.nasdaq.com/market-activity/index/ndx",
                            "LICENCE_UNKNOWN", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="licence_terms"),),
    ),
    SeriesSpec(
        key="DAX", description="German large cap performance index (total return by "
                               "construction).",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="performance index level -> monthly log returns",
        sources=(SourceSpec("Deutsche Boerse / STOXX", 1,
                            "https://www.stoxx.com/index-details?symbol=DAX",
                            "LICENCE_REQUIRED", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="licence_terms"),),
    ),
    SeriesSpec(
        key="EUROPE", description="Developed Europe equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="net total return index -> monthly log returns",
        sources=(SourceSpec("STOXX", 1, "https://www.stoxx.com/", "LICENCE_REQUIRED", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="licence_terms"),),
    ),
    SeriesSpec(
        key="JAPAN", description="Japanese equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="JPY", return_convention="total_return",
        transformation="TOPIX total return -> monthly log returns",
        sources=(SourceSpec("Japan Exchange Group", 1,
                            "https://www.jpx.co.jp/english/markets/indices/topix/",
                            "LICENCE_UNKNOWN", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="availability_and_licence_terms"),),
        blocker="No confirmed source mapping (known blocker in PROJECT_META Phase 4).",
    ),
    SeriesSpec(
        key="EM", description="Emerging markets equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="net total return index -> monthly log returns",
        sources=(
            SourceSpec("MSCI", 1, "https://www.msci.com/", "LICENCE_REQUIRED",
                       role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                       evidence_purpose="licence_terms"),
            SourceSpec("Kenneth R. French Data Library", 4,
                       "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
                       "Emerging_5_Factors_CSV.zip", "OPEN",
                       note="Shorter history than the developed set."),
        ),
        blocker="No confirmed source mapping (known blocker).",
    ),
    SeriesSpec(
        key="DIVIDEND", description="High dividend yield equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="net total return index -> monthly log returns",
        sources=(SourceSpec("MSCI", 1, "https://www.msci.com/", "LICENCE_REQUIRED",
                            role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                       evidence_purpose="licence_terms"),),
        blocker="No confirmed source mapping (known blocker).",
    ),
    SeriesSpec(
        key="COMMOD", description="Broad commodity index.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="index level -> monthly log returns",
        sources=(SourceSpec("Bloomberg", 5, "https://www.bloomberg.com/professional/"
                            "product/indices/bloomberg-commodity-index-family/",
                            "LICENCE_REQUIRED", role=EVIDENCE, evidence_kind=LICENCE_REQUIREMENT,
                            evidence_purpose="licence_terms"),),
        blocker="No confirmed source mapping (known blocker); tax class also unresolved.",
    ),

    # ---------------------------------------------------------------------
    # Macro series. These calibrate the inflation and short-rate processes and
    # therefore the Basiszins (B.2), so they are decision-path inputs even
    # though they are not assets.
    # ---------------------------------------------------------------------
    SeriesSpec(
        key="HICP_EA",
        description="Euro-area HICP, all items, annual rate of change. Calibrates the "
                    "inflation process used for all real-terms reporting.",
        required_for="every real-terms number in every phase",
        frequency="monthly", currency="index", return_convention="rate",
        transformation="annual rate of change -> monthly inflation for the OU calibration",
        sources=(SourceSpec("European Central Bank Data Portal (source: Eurostat)", 2,
                            "https://data-api.ecb.europa.eu/service/data/HICP/"
                            "M.U2.N.000000.4D0.ANR?format=csvdata", "OPEN",
                            note="KEY MIGRATED. The previous key ICP.M.U2.N.000000.4.ANR "
                                 "was discontinued 2026-02-04 after a methodological "
                                 "change and replaced by HICP.M.U2.N.000000.4D0.ANR. "
                                 "Externally reported coverage 1996-12 to 2026-05. "
                                 "Eurostat reuse permitted with attribution."),
                 SourceSpec("Eurostat", 3,
                            "https://ec.europa.eu/eurostat/api/dissemination/statistics/"
                            "1.0/data/prc_hicp_manr", "OPEN"),),
    ),
    SeriesSpec(
        key="CPI_DE",
        description="German consumer price index. The investor is German, so the "
                    "domestic deflator is the more faithful one.",
        required_for="real-terms reporting sensitivity",
        frequency="monthly", currency="index", return_convention="rate",
        transformation="index -> monthly inflation",
        sources=(SourceSpec("Statistisches Bundesamt (Destatis)", 3,
                            "https://www-genesis.destatis.de/genesisWS/rest/2020/data/"
                            "table?name=61111-0001", "OPEN",
                            note="GENESIS REST API requires free registration."),),
    ),
    SeriesSpec(
        key="SHORT_RATE_EA",
        description="Euro-area short-term interest rate.",
        required_for="B.2 - the Basiszins is a function of the modelled short rate",
        frequency="monthly", currency="rate", return_convention="rate",
        transformation="Native €STR from 2019-10 requires NO transformation. Extending "
                       "backwards with EONIA is a SPLICE: EONIA ran under its own "
                       "methodology to 2019-09-30, then was mechanically €STR + 8.5 bp "
                       "from 2019-10-02 until discontinuation on 2022-01-03. The splice "
                       "must carry its own documented rule and data_status and must never "
                       "be applied silently.",
        sources=(SourceSpec("Deutsche Bundesbank", 2,
                            "https://api.statistiken.bundesbank.de/rest/data/BBMMB/"
                            "M.EU000A2X2A25.WT?format=csv&lang=de", "OPEN",
                            note="Euro Short-Term Rate, monthly average. Externally "
                                 "reported as the official monthly series with CSV "
                                 "download; native coverage begins 2019-10. Reuse "
                                 "permitted with attribution, statistics and metadata "
                                 "not to be altered."),),
    ),
    SeriesSpec(
        key="BUND_LONG_YIELD",
        description="Yield on long-dated German government bonds - the reference the "
                    "statutory Basiszins is actually derived from.",
        required_for="B.2 Basiszins, currently legal_status TO_BE_VERIFIED",
        frequency="monthly", currency="rate", return_convention="rate",
        transformation="monthly average yield; compare against the published BMF "
                       "Basiszins values to validate the B.2 coupling",
        sources=(SourceSpec("Deutsche Bundesbank", 2,
                            "https://api.statistiken.bundesbank.de/rest/data/BBSIS/"
                            "M.I.UMR.RD.EUR.S1311.B.A604.A.R.A.A._Z._Z.A?format=csv&lang=de",
                            "OPEN",
                            note="CANDIDATE ONLY - MAPPING FROM WT3230 NOT SUPPORTED. "
                                 "Umlaufsrenditen inländischer Inhaberschuldverschreibungen "
                                 "/ börsennotierte Bundeswertpapiere, monthly. The legacy "
                                 "Externally reported 2026-08-21 (round 2): the official "
                                 "Bundesbank migration catalogue contains NO entry for "
                                 "BBK01.WT3230, so that key is almost certainly a "
                                 "SPECIFICATION ERROR in this registry rather than a "
                                 "renamed series. This candidate is documented as the "
                                 "successor of WU9555 / WU0115, NOT of WT3230. Concept: "
                                 "Umlaufsrenditen inlaendischer Inhaberschuldverschreibungen "
                                 "/ boersennotierte Bundeswertpapiere / monthly. The same "
                                 "Bundesbank table also carries maturity-band series "
                                 "(3-5, 5-8, 8-15, 15-30 years), and which one is correct "
                                 "depends on the Basiszins concept, not on the label."),),
        blocker="BBK01.WT3230 has no entry in the official migration catalogue: "
                "SPECIFICATION_ERROR_SUSPECTED. The candidate succeeds WU9555/WU0115, not "
                "WT3230, and may not be mapped until the intended economic concept is "
                "decided.",
    ),
)

SERIES_BY_KEY = {s.key: s for s in SERIES}

# Phase 4 acceptance depends only on the reduced universe of Phase 6.
REDUCED_UNIVERSE = ("CORE", "GOLD")
MACRO_SERIES = ("HICP_EA", "SHORT_RATE_EA", "BUND_LONG_YIELD")
STOP_IF_MISSING = ("CORE",)


# --------------------------------------------------------------------------
# TER / cost sourcing (B.4)
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class CostSourceSpec:
    instrument: str
    isin: str
    document_type: str
    url: str
    authority: str
    endpoint_status: str = "UNVERIFIED"


COST_SOURCES: tuple[CostSourceSpec, ...] = (
    # CORRECTED 2026-08-21: IE00BK5BQT80 is a VANGUARD fund, not State Street.
    CostSourceSpec("CORE", "IE00BK5BQT80", "PRIIPs KID + factsheet",
                   "https://fund-docs.vanguard.com/ie00bk5bqt80_priipskid_de.pdf",
                   "issuer (Vanguard)"),
    CostSourceSpec("SP500", "IE00B5BMR087", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("NASDAQ", "IE00B53SZB19", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    # CORRECTED 2026-08-21: IE00BK5BR626 is a VANGUARD fund, not State Street.
    CostSourceSpec("DIVIDEND", "IE00BK5BR626", "PRIIPs KID + factsheet",
                   "https://fund-docs.vanguard.com/", "issuer (Vanguard)"),
    CostSourceSpec("EUROPE", "LU0328475792", "PRIIPs KID + factsheet",
                   "https://etf.dws.com/", "issuer (DWS / Xtrackers)"),
    CostSourceSpec("DAX", "DE0005933931", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("JAPAN", "IE00B4L5YX21", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("EM", "IE00BKM4GZ66", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    # CORRECTED 2026-08-21: IE00B4ND3602 is iShares Physical Gold ETC
    # (BlackRock), not an Invesco product.
    CostSourceSpec("GOLD", "IE00B4ND3602", "PRIIPs KID + prospectus",
                   "https://www.blackrock.com/de/privatanleger/literature/kiid/",
                   "issuer (BlackRock / iShares)"),
    CostSourceSpec("COMMOD", "IE00BDFL4P12", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
)

# ISIN -> issuer and product identity.
#
# Three entries in COST_SOURCES were wrong before 2026-08-21 (CORE and DIVIDEND
# attributed to State Street, GOLD to Invesco). Those errors were possible
# because nothing tied an ISIN to a named product. This table closes that gap
# and is asserted by tests.
#
# STATUS: EXTERNALLY_REPORTED. These identities come from the round 1/2 data
# reports and have NOT been verified locally - no KID has been fetched or
# hashed here. They are recorded so a mismatch is detectable, not as verified
# fact.
PRODUCT_IDENTITY: dict[str, dict] = {
    "CORE":     {"isin": "IE00BK5BQT80", "issuer": "Vanguard",
                 "product": "Vanguard FTSE All-World UCITS ETF (Acc)",
                 "benchmark": "FTSE All-World NR USD", "base_currency": "USD",
                 "inception": "2019-07-23"},
    "SP500":    {"isin": "IE00B5BMR087", "issuer": "BlackRock / iShares",
                 "product": "iShares Core S&P 500 UCITS ETF (Acc)"},
    "NASDAQ":   {"isin": "IE00B53SZB19", "issuer": "BlackRock / iShares",
                 "product": "iShares NASDAQ 100 UCITS ETF (Acc)"},
    "DIVIDEND": {"isin": "IE00BK5BR626", "issuer": "Vanguard",
                 "product": "Vanguard FTSE All-World High Dividend Yield UCITS ETF (Acc)"},
    "EUROPE":   {"isin": "LU0328475792", "issuer": "DWS / Xtrackers",
                 "product": "Xtrackers STOXX Europe 600 UCITS ETF 1C"},
    "DAX":      {"isin": "DE0005933931", "issuer": "BlackRock / iShares",
                 "product": "iShares Core DAX UCITS ETF (DE) (Acc)"},
    "JAPAN":    {"isin": "IE00B4L5YX21", "issuer": "BlackRock / iShares",
                 "product": "iShares Core MSCI Japan IMI UCITS ETF (Acc)"},
    "EM":       {"isin": "IE00BKM4GZ66", "issuer": "BlackRock / iShares",
                 "product": "iShares Core MSCI EM IMI UCITS ETF (Acc)"},
    "GOLD":     {"isin": "IE00B4ND3602", "issuer": "BlackRock / iShares",
                 "product": "iShares Physical Gold ETC"},
    "COMMOD":   {"isin": "IE00BDFL4P12", "issuer": "BlackRock / iShares",
                 "product": "iShares Diversified Commodity Swap UCITS ETF (Acc)"},
}

PRODUCT_IDENTITY_STATUS = "EXTERNALLY_REPORTED_NOT_VERIFIED_LOCALLY"


# Tracking difference is NOT in a KID. It has to be derived from published NAV
# history against the index, or taken from the issuer's own annual TD
# disclosure, and is therefore a separate acquisition task.
TRACKING_DIFFERENCE_NOTE = (
    "Tracking difference is not disclosed in a PRIIPs KID. It must be derived from "
    "published fund NAV history against the licensed index series, or taken from an "
    "issuer TD disclosure. Deriving it requires the index history, which is the same "
    "licence blocker as CORE."
)


def registry_payload() -> dict:
    return {
        "required_common_months": REQUIRED_COMMON_MONTHS,
        "reduced_universe": list(REDUCED_UNIVERSE),
        "macro_series": list(MACRO_SERIES),
        "stop_if_missing": list(STOP_IF_MISSING),
        "series": [s.as_dict() for s in SERIES],
        "cost_sources": [asdict(c) for c in COST_SOURCES],
        "tracking_difference_note": TRACKING_DIFFERENCE_NOTE,
        "endpoint_verification": "Every url is an INTENDED endpoint recorded from "
                                 "specification. None has been confirmed to resolve, "
                                 "because this environment has no network path.",
    }


# --------------------------------------------------------------------------
# Specification conflicts surfaced by acquisition
# --------------------------------------------------------------------------
# Acquisition is not only about whether data exists. Establishing what the data
# actually IS can invalidate a decision taken earlier on an assumption about it.
SPECIFICATION_CONFLICTS: tuple[dict, ...] = (
    {
        "id": "B5_FX_VS_USD_BENCHMARK",
        "severity": "DECISION_RELEVANT",
        "status": "RESOLVED",
        "raised_at": "2026-08-21",
        "resolved_at": "2026-08-21",
        "resolved_by": "human_operator",
        "summary": (
            "The CORE benchmark is FTSE All-World NET RETURN in USD, but B.5 had been "
            "recorded as fx=EXCLUDED_BY_DESIGN with a rationale asserting that non-EUR "
            "returns could be read as EUR returns with FX absorbed into volatility."
        ),
        "resolution": (
            "option_b retained but redefined as EXCLUDED_AS_SEPARATE_STOCHASTIC_FACTOR. "
            "No separate stochastic FX factor is simulated, preserving the original "
            "motivation. Every non-EUR calibration series MUST be converted to EUR "
            "before return estimation - data preprocessing, not a modelled process. "
            "Supported claims are limited to EUR-investor total-return behaviour."
        ),
        "authoritative_record": ["config/fx.json", "docs/DECISIONS_20260821.md"],
        "verification": (
            "Phases 1-3 were re-run end to end after the revision and every frozen "
            "comparator hash was bit-identical, demonstrating the change moved no number."
        ),
    },
)


# --------------------------------------------------------------------------
# Three-dimensional data status (operator decision, 2026-08-21)
# --------------------------------------------------------------------------
# The earlier implementation collapsed three independent properties into one
# licence_status, which is what produced the wrong inference
# "not openly redistributable -> not available -> FAIL". They are separated
# here. See config/data_policy.json for the authoritative vocabulary.

AVAILABILITY = ("ACQUIRED", "LICENCE_REQUIRED", "NOT_FOUND", "INSUFFICIENT_HISTORY",
                "DATA_INVALID", "REGISTRATION_REQUIRED", "PAYWALLED")
REDISTRIBUTION = ("OPEN", "RESTRICTED", "UNKNOWN")
REPRODUCIBILITY = ("OPEN_REPRODUCIBLE", "LICENSED_REPRODUCIBLE", "NOT_REPRODUCIBLE")

# Fields a licensed file must carry for a second party to verify byte equality.
LICENSED_PROVENANCE_FIELDS = (
    "provider", "series_or_index_identity", "currency", "return_convention",
    "retrieval_date", "licence_classification", "original_filename", "sha256",
    "period_start", "period_end", "row_count", "transformation_specification",
    "acquisition_instructions",
)


def redistribution_from_licence(licence_status: str) -> str:
    return {"OPEN": "OPEN",
            "LICENCE_REQUIRED": "RESTRICTED",
            "LICENCE_UNKNOWN": "UNKNOWN"}.get(licence_status, "UNKNOWN")


def classify_reproducibility(availability: str, redistribution: str,
                             local_file_hashed: bool) -> str:
    """Reproducibility is about whether a second party can reconstruct the input.

    That is NOT the same as whether the bytes may be republished. A licensed
    file held outside the repository, with complete provenance and a recorded
    SHA-256, is reproducible for anyone holding the same legitimate source -
    they recompute the hash and compare. Weaker than open reproducibility, and
    must be labelled as such, but it is not irreproducible.
    """
    if availability != "ACQUIRED" or not local_file_hashed:
        return "NOT_REPRODUCIBLE"
    if redistribution == "OPEN":
        return "OPEN_REPRODUCIBLE"
    return "LICENSED_REPRODUCIBLE"


def licensed_provenance_complete(record: dict) -> tuple[bool, list[str]]:
    """Whether a licensed-data record carries everything the contract requires."""
    missing = [f for f in LICENSED_PROVENANCE_FIELDS
               if not str(record.get(f, "")).strip()]
    return (not missing), missing


def source_status_triple(source: SourceSpec, availability: str,
                         local_file_hashed: bool = False) -> dict:
    redistribution = redistribution_from_licence(source.licence_status)
    return {
        "availability_status": availability,
        "redistribution_status": redistribution,
        "reproducibility_status": classify_reproducibility(
            availability, redistribution, local_file_hashed),
    }

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


@dataclass(frozen=True)
class SourceSpec:
    """One candidate source for one series."""
    provider: str
    tier: int
    url: str
    licence_status: str          # OPEN | LICENCE_REQUIRED | LICENCE_UNKNOWN
    endpoint_status: str = "UNVERIFIED"
    note: str = ""


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
        description="Global all-country equity total return, EUR - the benchmark the "
                    "whole study is defined against. The tracked index is FTSE All-World, "
                    "NOT MSCI ACWI: IE00BK5BQT80 is the Vanguard FTSE All-World UCITS ETF "
                    "(Acc). An earlier version of this registry specified MSCI ACWI, which "
                    "is a different index with a different constituent methodology.",
        required_for="PHASE_5, PHASE_6, and every calibrated statement. CORE missing "
                     "is the one condition that forces STOP.",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="net total return index -> monthly log returns; EUR series taken "
                       "directly, never converted from USD without an FX series (FX is "
                       "EXCLUDED_BY_DESIGN per B.5)",
        sources=(
            SourceSpec("FTSE Russell", 1,
                       "https://www.lseg.com/en/ftse-russell/indices/all-world",
                       "LICENCE_UNKNOWN",
                       note="THE CORRECT TARGET INDEX. FTSE All-World Net Total Return "
                            "EUR is the benchmark of IE00BK5BQT80. Availability and "
                            "redistribution terms have NOT been established - this is the "
                            "open question that must be answered before any FAIL verdict "
                            "on CORE."),
            SourceSpec("MSCI", 1, "https://www.msci.com/end-of-day-data-search",
                       "LICENCE_REQUIRED",
                       note="MSCI ACWI. Externally reported 2026-08-21: no >=360-month "
                            "EUR net-total-return raw series verifiable for redistribution; "
                            "MSCI forbids reproduction without prior written consent. NOTE "
                            "this is NOT the index the CORE instrument tracks, so this "
                            "finding does not settle CORE."),
            SourceSpec("Kenneth R. French Data Library (Dartmouth)", 4,
                       "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
                       "Developed_3_Factors_CSV.zip", "LICENCE_UNKNOWN",
                       note="CANDIDATE PROXY ONLY - REJECTED as of 2026-08-21. NOT ACWI "
                            "and not FTSE All-World: developed markets only, USD not EUR, "
                            "no MSCI-style net-of-withholding-tax concept, no explicit "
                            "open-redistribution licence, and its international portfolios "
                            "use MSCI raw data to 2006 and Bloomberg thereafter, so the "
                            "licence problem is inherited rather than avoided. Using it "
                            "would require an explicit SPLICE rule and its own data_status; "
                            "it may not silently stand in for CORE."),
        ),
        blocker="Authoritative EUR net-total-return global equity history is "
                "licence-encumbered. MSCI ACWI confirmed LICENCE_REQUIRED (externally "
                "reported); FTSE All-World, the actually relevant index, NOT YET ASSESSED.",
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
                       "LICENCE_REQUIRED",
                       note="Externally reported 2026-08-21: LBMA moved historical tabular "
                            "precious-metal prices into the MyLBMA portal; access requires "
                            "an IBA licence, otherwise LBMA directs users to purchase from "
                            "ICE. The former open JSON endpoint "
                            "(prices.lbma.org.uk/json/gold_pm.json) is superseded."),
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
                       "LICENCE_REQUIRED",
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
                            "LICENCE_UNKNOWN"),),
    ),
    SeriesSpec(
        key="DAX", description="German large cap performance index (total return by "
                               "construction).",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="performance index level -> monthly log returns",
        sources=(SourceSpec("Deutsche Boerse / STOXX", 1,
                            "https://www.stoxx.com/index-details?symbol=DAX",
                            "LICENCE_REQUIRED"),),
    ),
    SeriesSpec(
        key="EUROPE", description="Developed Europe equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="EUR", return_convention="total_return",
        transformation="net total return index -> monthly log returns",
        sources=(SourceSpec("STOXX", 1, "https://www.stoxx.com/", "LICENCE_REQUIRED"),),
    ),
    SeriesSpec(
        key="JAPAN", description="Japanese equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="JPY", return_convention="total_return",
        transformation="TOPIX total return -> monthly log returns",
        sources=(SourceSpec("Japan Exchange Group", 1,
                            "https://www.jpx.co.jp/english/markets/indices/topix/",
                            "LICENCE_UNKNOWN"),),
        blocker="No confirmed source mapping (known blocker in PROJECT_META Phase 4).",
    ),
    SeriesSpec(
        key="EM", description="Emerging markets equity.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="net total return index -> monthly log returns",
        sources=(
            SourceSpec("MSCI", 1, "https://www.msci.com/", "LICENCE_REQUIRED"),
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
        sources=(SourceSpec("MSCI", 1, "https://www.msci.com/", "LICENCE_REQUIRED"),),
        blocker="No confirmed source mapping (known blocker).",
    ),
    SeriesSpec(
        key="COMMOD", description="Broad commodity index.",
        required_for="INDETERMINATE_BY_CONSTRUCTION under G1",
        frequency="monthly", currency="USD", return_convention="total_return",
        transformation="index level -> monthly log returns",
        sources=(SourceSpec("Bloomberg", 5, "https://www.bloomberg.com/professional/"
                            "product/indices/bloomberg-commodity-index-family/",
                            "LICENCE_REQUIRED"),),
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
                            note="CANDIDATE ONLY - EQUIVALENCE NOT ESTABLISHED. "
                                 "Umlaufsrenditen inländischer Inhaberschuldverschreibungen "
                                 "/ börsennotierte Bundeswertpapiere, monthly. The legacy "
                                 "key BBK01.WT3230 that this registry previously specified "
                                 "could not be mapped onto the current Bundesbank database "
                                 "structure (externally reported 2026-08-21). This series "
                                 "may NOT be mapped to BUND_LONG_YIELD until the yield "
                                 "concept originally meant by WT3230 is established."),),
        blocker="Legacy key BBK01.WT3230 not resolvable; candidate exists but equivalence "
                "is unproven.",
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
    CostSourceSpec("CORE", "IE00BK5BQT80", "PRIIPs KID + factsheet",
                   "https://www.ssga.com/de/en_gb/institutional/capabilities/etfs",
                   "issuer (State Street / SPDR)"),
    CostSourceSpec("SP500", "IE00B5BMR087", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("NASDAQ", "IE00B53SZB19", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("DIVIDEND", "IE00BK5BR626", "PRIIPs KID + factsheet",
                   "https://www.ssga.com/de/en_gb/institutional/capabilities/etfs",
                   "issuer (State Street / SPDR)"),
    CostSourceSpec("EUROPE", "LU0328475792", "PRIIPs KID + factsheet",
                   "https://etf.dws.com/", "issuer (DWS / Xtrackers)"),
    CostSourceSpec("DAX", "DE0005933931", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("JAPAN", "IE00B4L5YX21", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("EM", "IE00BKM4GZ66", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
    CostSourceSpec("GOLD", "IE00B4ND3602", "PRIIPs KID + prospectus",
                   "https://www.invesco.com/", "issuer (Invesco)"),
    CostSourceSpec("COMMOD", "IE00BDFL4P12", "PRIIPs KID + factsheet",
                   "https://www.ishares.com/de", "issuer (BlackRock / iShares)"),
)

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

"""Acquisition, failure classification, and coverage validation for R3.

The distinction this module exists to protect
---------------------------------------------
A sandbox or network policy that blocks egress is a property of the ENVIRONMENT.
Whether a data series is obtainable is a property of the WORLD. Confusing the
two would let an infrastructure limitation masquerade as a research finding -
"CORE data is unavailable" when the truth is "this container cannot open a
socket".

The separation is enforced structurally, not by convention:

  * `probe_egress()` tests canary hosts that are NOT data sources.
  * If the canary probe fails, the environment is NETWORK_BLOCKED and
    `classify()` REFUSES to return any source-level verdict at all. Every
    per-source result becomes NETWORK_BLOCKED regardless of what the individual
    attempt returned.
  * Only when egress is confirmed may a failure be attributed to the source
    (404 -> SOURCE_NOT_FOUND, origin 401/403 -> LICENCE_OR_AUTH_REQUIRED).

`research_verdict_admissible()` is the single gate the phase runner must consult
before writing any PASS / PARTIAL / FAIL.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .hashing import sha256_bytes, sha256_obj

# Environment-level outcomes. None of these is a statement about the data.
NETWORK_BLOCKED = "NETWORK_BLOCKED"
NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
NETWORK_DNS_FAILURE = "NETWORK_DNS_FAILURE"
ENVIRONMENT_OUTCOMES = frozenset({NETWORK_BLOCKED, NETWORK_TIMEOUT, NETWORK_DNS_FAILURE})

# Source-level outcomes. These ARE statements about the data, and may only be
# produced when egress is confirmed working.
ACQUIRED = "ACQUIRED"
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
LICENCE_OR_AUTH_REQUIRED = "LICENCE_OR_AUTH_REQUIRED"
DATA_INVALID = "DATA_INVALID"
SOURCE_OUTCOMES = frozenset({ACQUIRED, SOURCE_NOT_FOUND, LICENCE_OR_AUTH_REQUIRED,
                             DATA_INVALID})

CANARY_HOSTS = ("https://example.com/", "https://www.iana.org/domains/reserved")


@dataclass
class AttemptResult:
    url: str
    outcome: str
    http_status: int | None = None
    bytes_received: int = 0
    content_sha256: str | None = None
    error: str = ""
    retrieved_at_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    @property
    def is_environment_outcome(self) -> bool:
        return self.outcome in ENVIRONMENT_OUTCOMES


def _raw_fetch(url: str, timeout: float = 30.0) -> AttemptResult:
    """One HTTP attempt, with every failure mode kept distinguishable."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "portfolio-sim-r3/3.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return AttemptResult(url=url, outcome=ACQUIRED, http_status=resp.status,
                                 bytes_received=len(body),
                                 content_sha256=sha256_bytes(body))
    except urllib.error.HTTPError as exc:
        # An HTTP status from an origin we actually reached.
        status = exc.code
        if status == 404:
            outcome = SOURCE_NOT_FOUND
        elif status in (401, 403, 451):
            outcome = LICENCE_OR_AUTH_REQUIRED
        else:
            outcome = DATA_INVALID
        return AttemptResult(url=url, outcome=outcome, http_status=status,
                             error=f"HTTPError {status}: {exc.reason}")
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if isinstance(exc.reason, socket.timeout) or "timed out" in reason.lower():
            return AttemptResult(url=url, outcome=NETWORK_TIMEOUT, error=reason)
        if isinstance(exc.reason, socket.gaierror):
            return AttemptResult(url=url, outcome=NETWORK_DNS_FAILURE, error=reason)
        # Proxy CONNECT refusals, TLS tunnel failures, connection refused.
        return AttemptResult(url=url, outcome=NETWORK_BLOCKED, error=reason)
    except (ssl.SSLError, socket.timeout) as exc:
        return AttemptResult(url=url, outcome=NETWORK_BLOCKED, error=str(exc))
    except Exception as exc:  # pragma: no cover - defensive
        return AttemptResult(url=url, outcome=NETWORK_BLOCKED,
                             error=f"{type(exc).__name__}: {exc}")


@dataclass
class EgressProbe:
    egress_available: bool
    attempts: list[dict]
    proxy_env: dict
    detail: str

    def as_dict(self) -> dict:
        return asdict(self)


def probe_egress(hosts: tuple[str, ...] = CANARY_HOSTS, timeout: float = 20.0) -> EgressProbe:
    """Test canary hosts that are NOT data sources.

    Using non-data hosts is the point: if example.com is unreachable, nothing
    can be concluded about whether MSCI or the ECB would have served us data.
    """
    attempts = [asdict(_raw_fetch(h, timeout)) for h in hosts]
    ok = any(a["outcome"] == ACQUIRED for a in attempts)
    proxy_env = {k: os.environ.get(k, "") for k in
                 ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy")}
    detail = ("egress confirmed against at least one canary host"
              if ok else
              "no canary host reachable; egress is blocked at the environment level, so "
              "NO source-level conclusion about data availability is admissible")
    return EgressProbe(egress_available=ok, attempts=attempts, proxy_env=proxy_env,
                       detail=detail)


def classify(attempt: AttemptResult, egress: EgressProbe) -> str:
    """Final outcome for one attempt, given the environment's egress state.

    This is the guard. With egress blocked, a per-source failure carries no
    information about the source, so it is reported as NETWORK_BLOCKED even if
    the raw attempt produced something that looks source-specific.
    """
    if not egress.egress_available:
        return NETWORK_BLOCKED
    return attempt.outcome


def research_verdict_admissible(egress: EgressProbe) -> bool:
    """Whether this run may emit a PASS / PARTIAL / FAIL at all.

    Teil D lists `CORE-Daten nicht verfuegbar -> STOP` as a research outcome.
    That outcome may only be reached from evidence. Without egress there is no
    evidence, so no verdict - including FAIL - may be issued.
    """
    return egress.egress_available


# --------------------------------------------------------------------------
# data_manifest.csv
# --------------------------------------------------------------------------
MANIFEST_COLUMNS = (
    "series_key", "source_provider", "source_tier", "source_url", "retrieval_date_utc",
    "frequency", "currency", "return_convention", "period_start", "period_end",
    "n_observations", "sha256", "transformations", "licence_status", "data_status",
)


def manifest_row(series_key: str, source, attempt: AttemptResult, outcome: str,
                 transformation: str, frequency: str, currency: str,
                 return_convention: str) -> dict:
    """One data_manifest.csv row.

    Fields that are unknown because acquisition did not happen are left EMPTY,
    never filled with a placeholder. An empty period_start is honest; a guessed
    one is fabricated provenance.
    """
    acquired = outcome == ACQUIRED
    return {
        "series_key": series_key,
        "source_provider": source.provider,
        "source_tier": source.tier,
        "source_url": source.url,
        "retrieval_date_utc": attempt.retrieved_at_utc,
        "frequency": frequency,
        "currency": currency,
        "return_convention": return_convention,
        "period_start": "",
        "period_end": "",
        "n_observations": 0,
        "sha256": attempt.content_sha256 or "",
        "transformations": transformation,
        "licence_status": source.licence_status,
        "data_status": outcome if not acquired else "ACQUIRED",
    }


def write_manifest_csv(rows: list[dict], path: Path) -> Path:
    import csv
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(MANIFEST_COLUMNS))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in MANIFEST_COLUMNS})
    return path


# --------------------------------------------------------------------------
# Coverage validation and effective sample size
# --------------------------------------------------------------------------
def validate_coverage(rows: list[dict], required_months: int,
                      required_keys: tuple[str, ...]) -> dict:
    """Check the common-month coverage requirement across required series."""
    acquired = {r["series_key"]: r for r in rows if r.get("data_status") == "ACQUIRED"}
    missing = [k for k in required_keys if k not in acquired]
    if missing:
        return {"result": "INSUFFICIENT", "missing_series": missing,
                "common_months": 0, "required_months": required_months}
    counts = [int(acquired[k]["n_observations"]) for k in required_keys]
    common = min(counts) if counts else 0
    return {
        "result": "SUFFICIENT" if common >= required_months else "INSUFFICIENT",
        "missing_series": [],
        "common_months": common,
        "required_months": required_months,
    }


def effective_sample_size(total_years: float, window_years: float) -> dict:
    """Effective n for overlapping rolling windows - a Phase 4 mandatory note.

    PROJECT_META: rolling 20-year windows drawn from ~50 years of history contain
    about 1.5 independent observations, and P10/P90 of such overlapping windows
    must NOT be presented as a distribution.

    Three defensible counts are reported rather than one, because "effective n"
    is ambiguous and the ambiguity is material at these magnitudes. The
    PROJECT_META figure of ~1.5 corresponds to (T - h) / h.
    """
    if window_years <= 0 or total_years <= 0:
        raise ValueError("total_years and window_years must be positive")
    overlapping = max(0.0, (total_years - window_years)) * 12 + 1
    return {
        "total_years": total_years,
        "window_years": window_years,
        "overlapping_monthly_windows": int(overlapping),
        "non_overlapping_windows_floor": int(total_years // window_years),
        "non_overlapping_windows_exact": total_years / window_years,
        "independent_increments_T_minus_h_over_h": (total_years - window_years) / window_years,
        "project_meta_convention": "(T - h) / h",
        "reporting_rule": (
            "P10/P90 of overlapping rolling windows MUST NOT be presented as a "
            "distribution. Effective sample size must be stated alongside any such "
            "figure."
        ),
    }


def acquisition_report(egress: EgressProbe, rows: list[dict], coverage: dict,
                       effective_n: dict) -> dict:
    payload = {
        "egress_probe": egress.as_dict(),
        "research_verdict_admissible": research_verdict_admissible(egress),
        "manifest_rows": rows,
        "coverage": coverage,
        "effective_sample_size": effective_n,
        "outcome_vocabulary": {
            "environment_level": sorted(ENVIRONMENT_OUTCOMES),
            "source_level": sorted(SOURCE_OUTCOMES),
            "rule": "Environment-level outcomes are NEVER research findings. A "
                    "source-level outcome may only be recorded when egress is confirmed.",
        },
    }
    payload["report_hash"] = sha256_obj(payload)
    return payload

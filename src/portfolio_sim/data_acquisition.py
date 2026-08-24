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

from .hashing import sha256_bytes, sha256_file, sha256_obj

# Environment-level outcomes. None of these is a statement about the data.
NETWORK_BLOCKED = "NETWORK_BLOCKED"
NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
NETWORK_DNS_FAILURE = "NETWORK_DNS_FAILURE"
ENVIRONMENT_OUTCOMES = frozenset({NETWORK_BLOCKED, NETWORK_TIMEOUT, NETWORK_DNS_FAILURE})

# Source-level outcomes. These ARE statements about the data, and may only be
# produced when egress is confirmed working.
#
# HTTP_OK is deliberately NOT an acquisition. Fetching a landing page, a licence
# page or a marketing page returns 200 and tells you nothing about whether the
# series behind it was obtained. Conflating the two is how a successful network
# request turns into a false "data unavailable" verdict.
HTTP_OK = "HTTP_OK"                      # transport succeeded; content unclassified
EVIDENCE_CAPTURED = "EVIDENCE_CAPTURED"    # EVIDENCE source fetched; content NOT checked
EVIDENCE_VALIDATED = "EVIDENCE_VALIDATED"  # a validator confirmed the proposition in the body
DATA_ACQUIRED = "DATA_ACQUIRED"          # a DATA_ARTIFACT parsed to >0 observations
DATA_NOT_PARSED = "DATA_NOT_PARSED"      # 200 from a data artifact, but no series parsed
SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
LICENCE_OR_AUTH_REQUIRED = "LICENCE_OR_AUTH_REQUIRED"
DATA_INVALID = "DATA_INVALID"
SOURCE_OUTCOMES = frozenset({HTTP_OK, EVIDENCE_CAPTURED, EVIDENCE_VALIDATED,
                             DATA_ACQUIRED, DATA_NOT_PARSED,
                             SOURCE_NOT_FOUND, LICENCE_OR_AUTH_REQUIRED, DATA_INVALID})

# The only outcome that may ever set `acquired` on a series.
ACQUISITION_OUTCOMES = frozenset({DATA_ACQUIRED})

# Outcomes that constitute LOCALLY VALIDATED evidence.
#
# EVIDENCE_CAPTURED is deliberately NOT here. Fetching a page proves the page
# exists, not that it says what the registry claims it says. Only a validator
# that matched the proposition in the response body counts.
ACCESS_EVIDENCE_OUTCOMES = frozenset({LICENCE_OR_AUTH_REQUIRED, EVIDENCE_VALIDATED})

# Outcomes that constitute evidence the data itself is not there.
UNAVAILABILITY_EVIDENCE_OUTCOMES = frozenset({SOURCE_NOT_FOUND, DATA_INVALID})

# Retained for backward compatibility with older manifests. Never emitted.
ACQUIRED = DATA_ACQUIRED

CANARY_HOSTS = ("https://example.com/", "https://www.iana.org/domains/reserved")


@dataclass
class AttemptResult:
    url: str
    outcome: str
    http_status: int | None = None
    bytes_received: int = 0
    content_sha256: str | None = None
    error: str = ""
    # Response body, kept so evidence validators can inspect what the page
    # actually says. Excluded from every serialised record: it is raw remote
    # content, often large, and belongs in a validator, not in a manifest.
    body: bytes | None = field(default=None, repr=False)
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
            return AttemptResult(url=url, outcome=HTTP_OK, http_status=resp.status,
                                 bytes_received=len(body),
                                 content_sha256=sha256_bytes(body), body=body)
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
    ok = any(a["outcome"] == HTTP_OK for a in attempts)
    proxy_env = {k: os.environ.get(k, "") for k in
                 ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy")}
    detail = ("egress confirmed against at least one canary host"
              if ok else
              "no canary host reachable; egress is blocked at the environment level, so "
              "NO source-level conclusion about data availability is admissible")
    return EgressProbe(egress_available=ok, attempts=attempts, proxy_env=proxy_env,
                       detail=detail)


# --------------------------------------------------------------------------
# Evidence validators
# --------------------------------------------------------------------------
# A validator reads the response body and decides whether it actually asserts
# the proposition the registry files it under. These are deliberately
# CONSERVATIVE: each requires several independent markers, and anything it
# cannot confirm stays EVIDENCE_CAPTURED rather than becoming
# EVIDENCE_VALIDATED. A false negative costs a re-check; a false positive would
# manufacture a verdict, which is the failure mode this whole module exists to
# prevent.
#
# They are text heuristics over remote pages, so every result records the
# matched markers for human audit, and a validator_version so a later change is
# detectable.
VALIDATOR_VERSION = "1.0.0"


@dataclass
class ValidationResult:
    validator_id: str
    validated: bool
    matched_markers: list[str]
    validator_version: str = VALIDATOR_VERSION
    note: str = ""


def _markers_present(text: str, groups: tuple[tuple[str, ...], ...]) -> list[str]:
    """Return one matched phrase per group, or [] unless EVERY group matched.

    Requiring a hit in each group is what stops a single incidental word from
    validating a proposition.
    """
    lowered = text.lower()
    hits = []
    for group in groups:
        found = next((phrase for phrase in group if phrase in lowered), None)
        if found is None:
            return []
        hits.append(found)
    return hits


def validate_lseg_coverage_limit(text: str) -> ValidationResult:
    """Does the page state that freely available history is short (~2 years)?"""
    hits = _markers_present(text, (
        ("two years", "2 years", "24 months", "twenty-four months"),
        ("month-end", "month end", "monthly"),
        ("historic index values", "index values", "historical values"),
    ))
    return ValidationResult(
        "lseg_coverage_limit", bool(hits), hits,
        note="Requires a limited-duration phrase, a month-end/monthly phrase and an "
             "index-values phrase to co-occur.")


def validate_lseg_licence_requirement(text: str) -> ValidationResult:
    """Does the page state that use/distribution requires a licence?"""
    hits = _markers_present(text, (
        ("licence", "license", "licensing"),
        ("distribut", "redistribut", "reproduc"),
        ("index data", "index values", "ftse russell", "lseg"),
    ))
    return ValidationResult(
        "lseg_licence_requirement", bool(hits), hits,
        note="Requires licence language, distribution/reproduction language and an "
             "index-data reference to co-occur.")


VALIDATORS = {
    "lseg_coverage_limit": validate_lseg_coverage_limit,
    "lseg_licence_requirement": validate_lseg_licence_requirement,
}


def run_validator(validator_id: str, body: bytes | None) -> ValidationResult | None:
    """Run a registered validator over a response body.

    Returns None when there is nothing to validate - no validator declared, or
    no body. None is not a failure; it means the proposition was never checked,
    and the outcome stays EVIDENCE_CAPTURED.
    """
    if not validator_id or body is None:
        return None
    fn = VALIDATORS.get(validator_id)
    if fn is None:
        return ValidationResult(validator_id, False, [],
                                note="no validator registered under this id")
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:  # pragma: no cover - decode with errors= cannot raise
        return ValidationResult(validator_id, False, [], note="body not decodable")
    return fn(text)


def classify(attempt: AttemptResult, egress: EgressProbe,
             source_role: str = "DATA_ARTIFACT", n_observations: int = 0,
             validation: "ValidationResult | None" = None) -> str:
    """Final outcome for one attempt, given egress state, source role and content.

    Two guards, both load-bearing:

    1. With egress blocked, a per-source failure carries no information about the
       source, so everything collapses to NETWORK_BLOCKED even if the raw attempt
       produced something that looks source-specific.

    2. HTTP 200 IS NOT ACQUISITION. A landing page, a licence page or a product
       page returns 200 and contains no series. Only a DATA_ARTIFACT that parsed
       to at least one observation may become DATA_ACQUIRED; everything else that
       merely fetched is EVIDENCE_CAPTURED or DATA_NOT_PARSED. Without this, a
       successful fetch of an index provider's marketing page would be recorded
       as having obtained the index.
    """
    if not egress.egress_available:
        return NETWORK_BLOCKED
    if attempt.outcome != HTTP_OK:
        return attempt.outcome
    if source_role == "EVIDENCE":
        # Fetching the page is not the same as the page saying what we claim.
        if validation is not None and validation.validated:
            return EVIDENCE_VALIDATED
        return EVIDENCE_CAPTURED
    return DATA_ACQUIRED if n_observations > 0 else DATA_NOT_PARSED


def series_is_acquired(outcomes) -> bool:
    """A series counts as acquired ONLY on a parsed data artifact.

    Never on an HTTP 200, never on captured evidence. This is the single
    predicate the phase verdict may use.
    """
    return any(o in ACQUISITION_OUTCOMES for o in outcomes)


def has_access_evidence(outcomes) -> bool:
    """Any locally validated evidence of a licence or authorisation wall.

    Coarse. For CORE use `access_constraint_established`, which additionally
    requires the RIGHT propositions about the RIGHT series.
    """
    return any(o in ACCESS_EVIDENCE_OUTCOMES for o in outcomes)


def access_constraint_established(attempts, required_kinds, required_relation="EXACT"):
    """Whether an access constraint is proven for the EXACT series.

    `attempts` are per-source records carrying `outcome`, `series_relation`,
    `evidence_kind`. An attempt counts only when all three hold:

      * outcome is EVIDENCE_VALIDATED or LICENCE_OR_AUTH_REQUIRED - a validator
        actually confirmed the proposition, or the origin itself refused;
      * series_relation == required_relation - evidence about a PROXY or a
        DIFFERENT_INDEX says nothing about the exact series;
      * evidence_kind is one of `required_kinds`.

    EVERY required kind must be satisfied. For CORE that means a validated
    COVERAGE_LIMIT *and* a validated LICENCE_REQUIREMENT: knowing the public
    history is short does not by itself show the longer history is licensed, and
    knowing index data is licensed does not by itself show the free history is
    too short.

    Returns (established, detail).
    """
    required = set(required_kinds)
    satisfied, contributing = {}, []
    for a in attempts:
        outcome = a.get("outcome")
        if outcome not in ACCESS_EVIDENCE_OUTCOMES:
            continue
        if a.get("series_relation") != required_relation:
            continue
        kind = a.get("evidence_kind")
        if kind in required:
            satisfied[kind] = a.get("provider", "")
            contributing.append({"provider": a.get("provider"), "kind": kind,
                                 "outcome": outcome,
                                 "series_relation": a.get("series_relation")})
    missing = sorted(required - set(satisfied))
    return (not missing), {
        "required_kinds": sorted(required),
        "required_relation": required_relation,
        "satisfied_kinds": sorted(satisfied),
        "missing_kinds": missing,
        "contributing_sources": contributing,
        "rule": "Every required kind must be validated for the EXACT series. "
                "PROXY and DIFFERENT_INDEX evidence is excluded by construction.",
    }


def has_unavailability_evidence(outcomes) -> bool:
    """Locally validated evidence that the data itself is absent or unusable."""
    return any(o in UNAVAILABILITY_EVIDENCE_OUTCOMES for o in outcomes)


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
    "series_key", "source_provider", "source_tier", "source_role", "evidence_purpose",
    "source_url", "retrieval_date_utc",
    "frequency", "currency", "return_convention", "period_start", "period_end",
    "n_observations", "sha256", "transformations", "licence_status", "data_status",
)


def manifest_row(series_key: str, source, attempt: AttemptResult, outcome: str,
                 transformation: str, frequency: str, currency: str,
                 return_convention: str, n_observations: int = 0,
                 period_start: str = "", period_end: str = "") -> dict:
    """One data_manifest.csv row.

    Fields unknown because acquisition did not happen are left EMPTY, never
    filled with a placeholder. An empty period_start is honest; a guessed one is
    fabricated provenance.

    n_observations is only ever non-zero for a DATA_ACQUIRED artifact. An
    EVIDENCE row records that a page was read, not that a series was obtained.
    """
    acquired = outcome == DATA_ACQUIRED
    return {
        "series_key": series_key,
        "source_provider": source.provider,
        "source_tier": source.tier,
        "source_role": getattr(source, "role", "DATA_ARTIFACT"),
        "evidence_purpose": getattr(source, "evidence_purpose", ""),
        "source_url": source.url,
        "retrieval_date_utc": attempt.retrieved_at_utc,
        "frequency": frequency,
        "currency": currency,
        "return_convention": return_convention,
        "period_start": period_start if acquired else "",
        "period_end": period_end if acquired else "",
        "n_observations": n_observations if acquired else 0,
        "sha256": attempt.content_sha256 or "",
        "transformations": transformation,
        "licence_status": source.licence_status,
        "data_status": outcome,
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
    # Only a parsed data artifact counts. An EVIDENCE row or an HTTP_OK row
    # contributes nothing to coverage regardless of its HTTP status.
    acquired = {r["series_key"]: r for r in rows
                if r.get("data_status") == DATA_ACQUIRED and int(r.get("n_observations", 0)) > 0}
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


# --------------------------------------------------------------------------
# Licensed-file verification (item 4)
# --------------------------------------------------------------------------
# reproducibility != redistribution, but it does require that the bytes exist
# and match. A complete provenance record on its own proves nothing: it is a
# claim about a file, not the file.
#
# NOTE ON SCOPE: the row/period check below is a GENERIC CSV integrity check, not
# a calibration parser. It counts data rows and reads the first column of the
# first and last data row. It does not interpret HICP, EUR-STR or gold semantics,
# and building those parsers is explicitly out of scope here.

def _generic_csv_scan(path: Path) -> dict:
    """Count data rows and read first/last first-column values from a CSV."""
    import csv as _csv

    with Path(path).open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = _csv.reader(fh)
        rows = [r for r in reader if r and any(str(c).strip() for c in r)]
    if not rows:
        return {"row_count": 0, "first_key": "", "last_key": ""}
    data = rows[1:] if len(rows) > 1 else []
    if not data:
        return {"row_count": 0, "first_key": "", "last_key": ""}
    return {"row_count": len(data),
            "first_key": str(data[0][0]).strip(),
            "last_key": str(data[-1][0]).strip()}


def verify_licensed_file(record: dict, licensed_dir: Path) -> dict:
    """Verify a licensed file against its provenance record.

    Metadata completeness is necessary but never sufficient. All of these must
    hold before PASS_RESTRICTED_DATA may be issued:

      1. the provenance record carries every required field;
      2. the file named by `original_filename` exists under `licensed_dir`;
      3. its actual SHA-256 equals the recorded `sha256`;
      4. its row count equals the recorded `row_count`;
      5. its first and last keys equal `period_start` and `period_end`.
    """
    from .data_registry import licensed_provenance_complete

    failures = []
    complete, missing = licensed_provenance_complete(record)
    if not complete:
        failures.append(f"provenance incomplete: missing {missing}")

    filename = str(record.get("original_filename", "")).strip()
    path = Path(licensed_dir) / filename if filename else None
    file_present = bool(filename) and path.exists()
    if not file_present:
        failures.append(
            f"licensed file not present at {licensed_dir}/{filename or '<unnamed>'}. "
            "A provenance record is a claim about a file, not the file.")
        return {"verified": False, "file_present": False, "failures": failures,
                "provenance_complete": complete}

    actual_sha = sha256_file(path)
    sha_ok = actual_sha == str(record.get("sha256", "")).strip().lower()
    if not sha_ok:
        failures.append(f"sha256 mismatch: recorded {record.get('sha256')}, "
                        f"actual {actual_sha}")

    scan = _generic_csv_scan(path)
    try:
        expected_rows = int(record.get("row_count", -1))
    except (TypeError, ValueError):
        expected_rows = -1
    rows_ok = scan["row_count"] == expected_rows
    if not rows_ok:
        failures.append(f"row_count mismatch: recorded {record.get('row_count')}, "
                        f"actual {scan['row_count']}")

    start_ok = scan["first_key"] == str(record.get("period_start", "")).strip()
    end_ok = scan["last_key"] == str(record.get("period_end", "")).strip()
    if not start_ok:
        failures.append(f"period_start mismatch: recorded {record.get('period_start')}, "
                        f"actual {scan['first_key']}")
    if not end_ok:
        failures.append(f"period_end mismatch: recorded {record.get('period_end')}, "
                        f"actual {scan['last_key']}")

    return {
        "verified": not failures,
        "file_present": True,
        "provenance_complete": complete,
        "sha256_match": sha_ok,
        "row_count_match": rows_ok,
        "period_match": start_ok and end_ok,
        "actual": scan | {"sha256": actual_sha},
        "failures": failures,
        "scope_note": "Generic CSV integrity check, not a calibration parser.",
    }

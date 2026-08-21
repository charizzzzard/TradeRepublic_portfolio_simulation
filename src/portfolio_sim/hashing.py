"""Deterministic hashing of code, configuration and gate definitions.

Every phase must emit a run_manifest.json; a result without a manifest is not a
result (Teil C). Gate thresholds are hashed BEFORE a run so that a later change
to a threshold is technically detectable and therefore provably forbidden
(Phase 6, Gate-Freeze).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json(obj) -> bytes:
    """Stable serialisation: sorted keys, no incidental whitespace.

    Two structurally identical configs must hash identically regardless of how
    they were written.
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_obj(obj) -> str:
    return sha256_bytes(canonical_json(obj))


def hash_tree(root: Path, patterns: tuple[str, ...]) -> str:
    """Hash a set of files as one unit, path-ordered so the result is stable."""
    entries = []
    for pattern in patterns:
        entries.extend(sorted(Path(root).glob(pattern)))
    digest = hashlib.sha256()
    for path in sorted(set(entries)):
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def code_hash() -> str:
    return hash_tree(REPO_ROOT, ("src/portfolio_sim/*.py",))


def parameter_hash() -> str:
    return hash_tree(REPO_ROOT, ("config/*.json",))


def environment_hash() -> str:
    import platform
    import sys

    try:
        import numpy
        numpy_version = numpy.__version__
    except Exception:  # pragma: no cover - numpy is a hard dependency
        numpy_version = "absent"
    return sha256_obj({
        "python": sys.version.split()[0],
        "platform": platform.system(),
        "machine": platform.machine(),
        "numpy": numpy_version,
    })


def git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if out.returncode == 0:
            return out.stdout.strip()
        return "UNCOMMITTED"
    except Exception:
        return "UNAVAILABLE"

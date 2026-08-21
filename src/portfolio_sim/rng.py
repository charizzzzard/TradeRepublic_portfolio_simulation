"""Common Random Numbers (CRN).

A.5 makes CRN mandatory: every portfolio must see the SAME random streams, so
that a paired comparison measures the portfolio difference and not a difference
in draws.

The guarantee is structural, not conventional: shocks are drawn for the FULL
asset universe in a fixed canonical order and a fixed shape, from a seed that
depends only on (master_seed, world_index). A portfolio then *indexes into*
that block. It is therefore impossible for a portfolio's composition to change
the numbers any other portfolio sees.
"""
from __future__ import annotations

import numpy as np

# Canonical universe order. Appending is safe; reordering or inserting breaks
# CRN comparability with every previously published run.
UNIVERSE = (
    "CORE", "SP500", "NASDAQ", "DIVIDEND", "EUROPE",
    "DAX", "JAPAN", "EM", "GOLD", "COMMOD",
)
ASSET_INDEX = {name: i for i, name in enumerate(UNIVERSE)}

# Macro factors are drawn from the same block so that an inflation world and the
# asset paths inside it stay coupled (B.2 rationale).
MACRO_FACTORS = ("inflation", "short_rate")


def world_seed(master_seed: int, world: int) -> int:
    """Seed for one parameter world, independent of portfolio and of asset count."""
    return int(master_seed) * 1_000_003 + int(world)


class CRNBlock:
    """Immutable block of standard-normal shocks shared by all portfolios."""

    __slots__ = ("asset_shocks", "macro_shocks", "n_paths", "n_months", "seed",
                 "_corr_key", "_all_correlated")

    def __init__(self, master_seed: int, world: int, n_paths: int, n_months: int):
        self.seed = world_seed(master_seed, world)
        self.n_paths = n_paths
        self.n_months = n_months
        gen = np.random.default_rng(self.seed)
        # Draw order is fixed: assets first, then macro. Never reorder.
        self.asset_shocks = gen.standard_normal((n_paths, n_months, len(UNIVERSE)))
        self.macro_shocks = gen.standard_normal((n_paths, n_months, len(MACRO_FACTORS)))
        self._corr_key = None
        self._all_correlated = None
        self.asset_shocks.setflags(write=False)
        self.macro_shocks.setflags(write=False)

    def correlated(self, assets: tuple[str, ...], full_corr: np.ndarray) -> np.ndarray:
        """Correlated shocks for `assets`, shape (n_paths, n_months, len(assets)).

        `full_corr` is the correlation matrix of the ENTIRE canonical universe,
        in UNIVERSE order - never a sub-matrix of just `assets`.

        That distinction is the whole CRN guarantee. If each portfolio factored
        only its own sub-matrix, a shared asset's correlated shock would depend
        on which OTHER assets happened to be in the portfolio, and a paired
        comparison would silently stop being paired. Factoring the full
        universe and slicing columns means asset j's shock is a fixed function
        of the shared draws, identical in every portfolio.
        """
        full_corr = np.asarray(full_corr, dtype=float)
        n = len(UNIVERSE)
        if full_corr.shape != (n, n):
            raise ValueError(
                f"full_corr must be {n}x{n} over the canonical universe, got "
                f"{full_corr.shape}. Pass a full-universe matrix (see full_corr_from)."
            )
        key = full_corr.tobytes()
        if key != self._corr_key:
            factor = cholesky_psd(full_corr)
            self._all_correlated = self.asset_shocks @ factor.T
            self._all_correlated.setflags(write=False)
            self._corr_key = key
        idx = [ASSET_INDEX[a] for a in assets]
        return self._all_correlated[:, :, idx]

    def macro(self, factor: str) -> np.ndarray:
        return self.macro_shocks[:, :, MACRO_FACTORS.index(factor)]


def cholesky_psd(corr: np.ndarray, negative_tol: float = 1e-10) -> np.ndarray:
    """A factor L with L @ L.T == corr, used to correlate the shared shocks.

    Three cases, in order:

    1. `corr` is positive DEFINITE -> the ordinary Cholesky factor. This is the
       normal path and is untouched by the fallbacks below, so parameter worlds
       drawn in the interior are unaffected by them.

    2. `corr` is positive SEMI-definite but singular (rank deficient), which is
       exactly what perfect correlation produces. `np.linalg.cholesky` rejects
       this even though it is a legitimate correlation matrix. The symmetric
       eigen square root reproduces it EXACTLY, with no perturbation: clipping
       an eigenvalue that is already zero to zero changes nothing, and no
       renormalisation is applied. This matters because perturbing two
       perfectly correlated assets apart makes them drift, which triggers
       spurious rebalancing trades and spurious realised gains.

    3. `corr` has a materially negative eigenvalue -> it is not a correlation
       matrix. It is repaired and renormalised, and the caller can detect that
       by comparing L @ L.T against the input. Repair exists so a parameter
       world sampled near the PSD boundary does not abort a run.
    """
    corr = np.asarray(corr, dtype=float)
    try:
        return np.linalg.cholesky(corr)
    except np.linalg.LinAlgError:
        pass

    vals, vecs = np.linalg.eigh(corr)
    if vals.min() >= -negative_tol:
        # Case 2: exactly PSD. Square root, no clipping of anything nonzero.
        return vecs @ np.diag(np.sqrt(np.clip(vals, 0.0, None)))

    # Case 3: not a correlation matrix. Repair, then renormalise the diagonal.
    vals = np.clip(vals, negative_tol, None)
    repaired = vecs @ np.diag(vals) @ vecs.T
    d = np.sqrt(np.diag(repaired))
    repaired = repaired / np.outer(d, d)
    return np.linalg.cholesky(repaired)


def full_corr_from(pairs: dict[tuple[str, str], float], default: float = 0.0) -> np.ndarray:
    """Build a full-universe correlation matrix from named pairwise entries.

    Every asset in UNIVERSE gets a row and column, whether or not any portfolio
    uses it, so that the factorisation - and therefore every asset's shock - is
    invariant to portfolio composition.
    """
    n = len(UNIVERSE)
    corr = np.full((n, n), float(default))
    np.fill_diagonal(corr, 1.0)
    for (a, b), rho in pairs.items():
        i, j = ASSET_INDEX[a], ASSET_INDEX[b]
        corr[i, j] = corr[j, i] = float(rho)
    return corr

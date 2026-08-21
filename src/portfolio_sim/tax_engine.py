"""German investment taxation for the decision path.

Scope (Teil B):
  * Abgeltungsteuer 25% + Solidaritaetszuschlag 5.5% on the tax (26.375%),
    church tax as a sensitivity only (A.4).
  * Teilfreistellung 30% for equity funds (§20 InvStG).
  * Vorabpauschale (§18 InvStG) with per-lot twelfths proration, cap at the
    Wertsteigerung of the year, floor 0, deemed accrued on the first working
    day of the following calendar year, and reduction of the disposal gain by
    accumulated Vorabpauschalen (§19 InvStG).
  * Basiszins coupled to the modelled short rate (B.2, see macro.py).
  * Sparer-Pauschbetrag / Freistellungsauftrag, annual reset.
  * GOLD as an ETC debt security under both B.3 variants.

Deliberately NOT in the decision path (B.1): the foreign-withholding-tax credit.
It is implemented and tested below, and it is CORRECT here, but no decision-path
run exercises it and NO GATE MAY DEPEND ON IT. See `credit_is_in_decision_path`.

All functions are vectorised over paths (axis 0).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SOLI_RATE = 0.055
EST_RATE = 0.25


# --------------------------------------------------------------------------
# Rate mechanics
# --------------------------------------------------------------------------
def abgeltungsteuer(
    kapitalertrag,
    church_rate: float = 0.0,
    foreign_wht=0.0,
):
    """Tax on `kapitalertrag` (already net of Teilfreistellung and FSA).

    Implements §32d Abs.1 EStG:

        e     = (K - 4q) / (4 + k)
        total = e * (1 + soli + k)

    where k is the church-tax rate as a DECIMAL FRACTION (9% -> 0.09), not as a
    percentage. With k = 0 and q = 0 this reduces to 0.25 * K * 1.055 =
    0.26375 * K; with k = 0.09 it gives the statutory 0.279951.

    The `- 4q` term is the foreign-withholding-tax credit. It credits q against
    the 25% Einkommensteuer, with the Solidaritaetszuschlag applied AFTERWARDS
    to the reduced amount. That is the correction of the v2 defect, which
    credited against 26.375% directly. q is 0 on every decision path (B.1).
    """
    kapitalertrag = np.asarray(kapitalertrag, dtype=float)
    q = np.asarray(foreign_wht, dtype=float)
    est = (kapitalertrag - 4.0 * q) / (4.0 + church_rate)
    est = np.maximum(est, 0.0)  # a credit can never create a refund here
    return est * (1.0 + SOLI_RATE + church_rate)


def effective_rate(church_rate: float = 0.0) -> float:
    """Effective marginal rate on one euro of taxable Kapitalertrag."""
    return float(abgeltungsteuer(np.array([1.0]), church_rate)[0])


def credit_is_in_decision_path(tax_cfg: dict) -> bool:
    """B.1 guard: the withholding-credit branch must never gate a run."""
    return tax_cfg["withholding_tax_credit"]["status"] != "NOT_IN_DECISION_PATH"


# --------------------------------------------------------------------------
# Freistellungsauftrag
# --------------------------------------------------------------------------
@dataclass
class FSA:
    """Annual Sparer-Pauschbetrag, consumed chronologically within a year."""

    annual_eur: float
    n_paths: int
    tolerance: float = 1e-8
    remaining: np.ndarray = field(init=False)

    def __post_init__(self):
        self.remaining = np.full(self.n_paths, float(self.annual_eur))

    def reset(self):
        self.remaining[:] = float(self.annual_eur)

    def apply(self, taxable: np.ndarray) -> np.ndarray:
        """Absorb `taxable` against the remaining allowance; return the excess."""
        taxable = np.maximum(np.asarray(taxable, dtype=float), 0.0)
        used = np.minimum(taxable, self.remaining)
        self.remaining -= used
        # Clamp float dust so the cap holds to fsa_cap_tolerance_eur (A.5).
        np.clip(self.remaining, 0.0, float(self.annual_eur), out=self.remaining)
        self.remaining[np.abs(self.remaining) < self.tolerance] = 0.0
        return taxable - used


# --------------------------------------------------------------------------
# Vorabpauschale
# --------------------------------------------------------------------------
def basisertrag(nav_start_of_year, basiszins, factor: float = 0.7, twelfths: float = 1.0):
    """§18 InvStG Basisertrag = NAV_start_of_year * 0.7 * Basiszins * twelfths."""
    return np.asarray(nav_start_of_year, dtype=float) * factor * np.asarray(basiszins, dtype=float) * twelfths


def vorabpauschale(nav_start_of_year, basiszins, wertsteigerung, factor: float = 0.7, twelfths: float = 1.0):
    """Vorabpauschale for one lot: capped at the Wertsteigerung, floored at 0."""
    be = basisertrag(nav_start_of_year, basiszins, factor, twelfths)
    ws = np.maximum(np.asarray(wertsteigerung, dtype=float), 0.0)
    return np.maximum(np.minimum(be, ws), 0.0)


def acquisition_twelfths(month_in_year: int) -> float:
    """Twelfths factor for a lot acquired in `month_in_year` (1..12).

    §18 Abs.1 S.3 InvStG: the Basisertrag is reduced by one twelfth for each
    FULL month preceding the month of acquisition. January -> 12/12,
    March -> 10/12, December -> 1/12.
    """
    if not 1 <= month_in_year <= 12:
        raise ValueError(f"month_in_year must be 1..12, got {month_in_year}")
    return (13 - month_in_year) / 12.0


# --------------------------------------------------------------------------
# Tax classes
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class TaxClass:
    name: str
    teilfreistellung: float
    vorabpauschale_applies: bool
    holding_period_exemption_months: int | None = None

    @staticmethod
    def equity_fund(tax_cfg: dict) -> "TaxClass":
        return TaxClass("equity_fund", tax_cfg["teilfreistellung"]["equity_fund"], True, None)

    @staticmethod
    def gold(tax_cfg: dict, variant: str) -> "TaxClass":
        key = {
            "B3_assumed": "etc_debt_security_B3_assumed",
            "B3_alternative": "etc_debt_security_B3_alternative",
        }[variant]
        spec = tax_cfg["assets_tax_classes"][key]
        years = spec.get("holding_period_exemption_years")
        return TaxClass(
            f"etc_{variant}",
            spec["teilfreistellung"],
            False,
            None if years is None else int(years) * 12,
        )

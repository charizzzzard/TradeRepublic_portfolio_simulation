"""Per-asset lot ledger.

Lots are kept for the whole horizon rather than consolidated at year end,
because two different rules need acquisition dates:

  * the Vorabpauschale twelfths proration in the year of acquisition
    (§18 Abs.1 S.3 InvStG), and
  * the holding-period exemption in the B.3 GOLD contrast variant.

Arrays are (n_paths, n_lots). Lot 0 is the initial investment.
"""
from __future__ import annotations

import numpy as np

from .tax_engine import acquisition_twelfths, vorabpauschale


class Position:
    """Holding in one asset, tracked at lot granularity, vectorised over paths."""

    def __init__(self, n_paths: int, max_lots: int, tax_class):
        self.n_paths = n_paths
        self.tax_class = tax_class
        self.shares = np.zeros((n_paths, max_lots))
        self.cost_per_share = np.zeros((n_paths, max_lots))
        self.acq_month = np.full(max_lots, -1, dtype=int)
        self.n_lots = 0
        # Accumulated Vorabpauschalen already taxed; reduce the gain on disposal
        # (§19 InvStG). Aggregate is sufficient: no tax class in this universe
        # has BOTH a Vorabpauschale and a holding-period exemption.
        self.accum_vap = np.zeros(n_paths)
        self.price_at_year_start = None

    # -- trading ---------------------------------------------------------
    def buy(self, amount_eur: np.ndarray, price: np.ndarray, month: int):
        """Buy `amount_eur` worth at `price`. `amount_eur` is already net of costs."""
        amount_eur = np.maximum(np.asarray(amount_eur, dtype=float), 0.0)
        i = self.n_lots
        if i >= self.shares.shape[1]:
            raise IndexError(
                f"lot ledger exhausted ({i} lots): max_lots must budget for monthly "
                "purchases plus one rebalancing purchase per year boundary."
            )
        self.shares[:, i] = amount_eur / price
        self.cost_per_share[:, i] = price
        self.acq_month[i] = month
        self.n_lots += 1

    def market_value(self, price: np.ndarray) -> np.ndarray:
        return self.shares[:, : self.n_lots].sum(axis=1) * price

    def total_shares(self) -> np.ndarray:
        return self.shares[:, : self.n_lots].sum(axis=1)

    # -- disposal --------------------------------------------------------
    def realise(self, fraction: np.ndarray, price: np.ndarray, month: int) -> dict:
        """Sell `fraction` (per path, 0..1) of every lot pro rata.

        Returns proceeds and the taxable gain BEFORE Teilfreistellung and FSA.
        """
        fraction = np.clip(np.asarray(fraction, dtype=float), 0.0, 1.0)[:, None]
        n = self.n_lots
        sold = self.shares[:, :n] * fraction
        proceeds = sold.sum(axis=1) * price
        basis = (sold * self.cost_per_share[:, :n]).sum(axis=1)

        exempt_months = self.tax_class.holding_period_exemption_months
        if exempt_months is not None:
            held = month - self.acq_month[:n]
            taxable_lot = (held < exempt_months)[None, :]
            gross_gain = (sold * taxable_lot * (price[:, None] - self.cost_per_share[:, :n])).sum(axis=1)
        else:
            gross_gain = proceeds - basis

        # §19 InvStG: reduce the gain by the Vorabpauschalen already taxed,
        # pro rata to the fraction disposed of.
        vap_released = self.accum_vap * fraction[:, 0]
        gain = gross_gain - vap_released
        self.accum_vap -= vap_released

        self.shares[:, :n] -= sold
        return {"proceeds": proceeds, "gain": gain, "gross_gain": gross_gain, "basis": basis}

    # -- Vorabpauschale --------------------------------------------------
    def start_year(self, price: np.ndarray):
        self.price_at_year_start = np.array(price, dtype=float, copy=True)

    def year_end_vorabpauschale(self, price_end: np.ndarray, basiszins: np.ndarray,
                                year_start_month: int, factor: float = 0.7) -> np.ndarray:
        """Vorabpauschale for the calendar year just ended, summed over lots.

        Computed per lot because the twelfths proration and the Wertsteigerung
        cap are both per-lot quantities. Returns the GROSS amount, before
        Teilfreistellung and before the FSA.
        """
        if not self.tax_class.vorabpauschale_applies:
            return np.zeros(self.n_paths)

        p_start = self.price_at_year_start
        total = np.zeros(self.n_paths)
        for i in range(self.n_lots):
            shares = self.shares[:, i]
            if not np.any(shares > 0):
                continue
            acq = self.acq_month[i]
            if acq < year_start_month:
                # Held for the whole year: full twelfths, reference is the
                # price at the start of the calendar year.
                twelfths = 1.0
                ref_price = p_start
            else:
                twelfths = acquisition_twelfths(acq - year_start_month + 1)
                ref_price = self.cost_per_share[:, i]
            nav_start = shares * p_start
            wertsteigerung = shares * (price_end - ref_price)
            total += vorabpauschale(nav_start, basiszins, wertsteigerung, factor, twelfths)
        return total

    def register_taxed_vorabpauschale(self, gross_vap: np.ndarray):
        """Record the Vorabpauschale so it later reduces the disposal gain."""
        self.accum_vap += gross_vap

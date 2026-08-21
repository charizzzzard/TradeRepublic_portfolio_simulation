"""Cost model (Teil B.4).

Costs are a first-class parameter class because a 0.20 pp TER delta runs
directly against the 0.124 pp portfolio-CAGR materiality gate derived in G1.

TER and tracking difference are accrued monthly pro rata against the asset
price. Spread is charged on both sides of a trade. Savings-plan execution fees
and FX conversion are charged per execution.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CostSpec:
    ter: float = 0.0
    tracking_difference: float = 0.0
    spread: float = 0.0
    savings_plan_execution_eur: float = 0.0
    fx_conversion: float = 0.0

    @property
    def annual_drag(self) -> float:
        """Combined price-level drag per year (TER + tracking difference)."""
        return self.ter + self.tracking_difference

    def monthly_drag_factor(self) -> float:
        """Multiplicative monthly factor applied to the gross price path."""
        return float(np.exp(-np.log1p(self.annual_drag) / 12.0))

    def buy_net_of_costs(self, gross_eur):
        """Cash actually invested after spread, execution fee and FX."""
        gross_eur = np.asarray(gross_eur, dtype=float)
        net = gross_eur * (1.0 - self.spread - self.fx_conversion) - self.savings_plan_execution_eur
        return np.maximum(net, 0.0)

    def sell_net_of_costs(self, gross_eur):
        gross_eur = np.asarray(gross_eur, dtype=float)
        return np.maximum(gross_eur * (1.0 - self.spread - self.fx_conversion), 0.0)


def spec_for(instrument: str, costs_cfg: dict, ter_delta_bp: float = 0.0) -> CostSpec:
    """Build a CostSpec, optionally adding a TER delta for the Phase 3 sweep."""
    row = costs_cfg["instruments"][instrument]
    return CostSpec(
        ter=row["ter"] + ter_delta_bp / 10_000.0,
        tracking_difference=row["tracking_difference"],
        spread=row["spread"],
        savings_plan_execution_eur=row["savings_plan_execution_eur"],
        fx_conversion=row["fx_conversion"],
    )

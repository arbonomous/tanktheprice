"""Scenario Stress-Test Simulator projecting Brent & WTI price impact from Hormuz VLCC/AIS disruptions."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class StressProjectionDay:
    day: int
    label: str
    baseline_brent: float
    stressed_brent: float
    baseline_wti: float
    stressed_wti: float


@dataclass
class StressTestResult:
    vlcc_drop_pct: float
    ais_spoofing_multiplier: float
    congestion_surge_pct: float
    duration_days: int
    projected_supply_shock_score: float
    disrupted_mbbl_per_day: float
    brent_base_price: float
    brent_projected_price: float
    brent_delta_usd: float
    brent_delta_pct: float
    wti_base_price: float
    wti_projected_price: float
    wti_delta_usd: float
    wti_delta_pct: float
    risk_regime: str
    projection_curve: list[StressProjectionDay]


def run_stress_test(
    brent_spot: float,
    wti_spot: float,
    current_shock_score: float,
    baseline_outbound_mbbl: float,
    vlcc_drop_pct: float = 30.0,
    ais_spoofing_multiplier: float = 2.0,
    congestion_surge_pct: float = 25.0,
    duration_days: int = 5,
) -> StressTestResult:
    """
    Estimate Brent & WTI price impact using empirical seaborne supply elasticity:
    - Strait of Hormuz carries ~20% of global petroleum liquids (~17-21 Mbbl/d).
    - Short-run crude oil price elasticity of supply is highly inelastic (~-0.06 to -0.10),
      creating convex risk premia as VLCC transits drop by 15%, 30%, or 50%.
    """
    vlcc_drop = max(0.0, min(80.0, vlcc_drop_pct))
    ais_mult = max(1.0, min(6.0, ais_spoofing_multiplier))
    cong_surge = max(0.0, min(100.0, congestion_surge_pct))
    dur = max(1, min(21, int(duration_days)))

    # VLCCs represent ~62% of outbound Hormuz barrel volume; nonlinear spillover hits Suezmax/Aframax too
    effective_volume_loss_share = (vlcc_drop / 100.0) * 0.72 + ((vlcc_drop / 100.0) ** 1.6) * 0.25
    disrupted_mbbl = round(baseline_outbound_mbbl * min(0.85, effective_volume_loss_share), 2)

    # Convex supply-shock percentage impact on Brent (seaborne benchmark)
    duration_factor = 0.65 + 0.35 * math.log1p(dur) / math.log1p(7.0)
    flow_impact_pct = (0.19 * vlcc_drop + 0.0022 * (vlcc_drop ** 2)) * duration_factor
    ais_risk_premium_pct = max(0.0, (ais_mult - 1.0) * 1.15)
    congestion_premium_pct = (cong_surge / 100.0) * 2.1

    brent_delta_pct = round(min(48.0, flow_impact_pct + ais_risk_premium_pct + congestion_premium_pct), 2)
    # WTI tracks Brent at ~0.86 beta on Middle East chokepoint shocks
    wti_delta_pct = round(brent_delta_pct * 0.86, 2)

    brent_delta_usd = round(brent_spot * (brent_delta_pct / 100.0), 2)
    wti_delta_usd = round(wti_spot * (wti_delta_pct / 100.0), 2)

    projected_shock = round(
        max(
            -100.0,
            min(
                100.0,
                current_shock_score
                + vlcc_drop * 1.35
                + (ais_mult - 1.0) * 9.5
                + cong_surge * 0.25,
            ),
        ),
        1,
    )

    if projected_shock >= 75:
        regime = "SEVERE CHOKEPOINT CRISIS"
    elif projected_shock >= 45:
        regime = "ELEVATED SUPPLY SQUEEZE"
    elif projected_shock >= 20:
        regime = "MODERATE TIGHTENING"
    else:
        regime = "NORMAL TRANSIT REGIME"

    # Build 7-day forward price trajectory (S-curve shock absorption peaking around day 3-5)
    curve: list[StressProjectionDay] = []
    for day in range(0, 8):
        if day == 0:
            frac = 0.0
        else:
            ramp = 1.0 - math.exp(-day / max(1.4, dur * 0.45))
            # Mild mean reversion after disruption duration ends
            decay = 1.0 if day <= dur else math.exp(-(day - dur) * 0.14)
            frac = ramp * decay

        base_b = round(brent_spot * (1.0 + 0.0012 * day), 2)
        base_w = round(wti_spot * (1.0 + 0.0010 * day), 2)
        stress_b = round(base_b + brent_delta_usd * frac, 2)
        stress_w = round(base_w + wti_delta_usd * frac, 2)
        curve.append(
            StressProjectionDay(
                day=day,
                label="Spot" if day == 0 else f"T+{day}d",
                baseline_brent=base_b,
                stressed_brent=stress_b,
                baseline_wti=base_w,
                stressed_wti=stress_w,
            )
        )

    return StressTestResult(
        vlcc_drop_pct=round(vlcc_drop, 1),
        ais_spoofing_multiplier=round(ais_mult, 2),
        congestion_surge_pct=round(cong_surge, 1),
        duration_days=dur,
        projected_supply_shock_score=projected_shock,
        disrupted_mbbl_per_day=disrupted_mbbl,
        brent_base_price=round(brent_spot, 2),
        brent_projected_price=round(brent_spot + brent_delta_usd, 2),
        brent_delta_usd=brent_delta_usd,
        brent_delta_pct=brent_delta_pct,
        wti_base_price=round(wti_spot, 2),
        wti_projected_price=round(wti_spot + wti_delta_usd, 2),
        wti_delta_usd=wti_delta_usd,
        wti_delta_pct=wti_delta_pct,
        risk_regime=regime,
        projection_curve=curve,
    )

"""Chokepoint Congestion & Loitering Index calculator (speed < 3 knots outside designated anchorages)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from services.maritime_feed.base import DailyTransitPoint, VesselSnapshot
from services.signal_engine.geometry import (
    CONGESTION_HUBS,
    haversine_nm,
    is_congestion_loitering,
    is_in_tss_lane,
)


@dataclass
class CongestionMetricsResult:
    congestion_index: float  # 0 to 100
    loitering_vessels_count: int
    fujairah_loitering: int
    bandar_abbas_loitering: int
    tss_lane_loitering: int
    avg_transit_speed_knots: float
    congestion_zscore: float


def compute_congestion_index(
    vessels: Sequence[VesselSnapshot],
    daily_transits: Sequence[DailyTransitPoint],
) -> CongestionMetricsResult:
    """Flag tankers idling (< 3 kn) near Fujairah, Bandar Abbas, or inside TSS outside anchorages."""
    loitering = [v for v in vessels if is_congestion_loitering(v.lat, v.lon, v.speed_knots) or v.status == "loitering"]

    fujairah_cnt = 0
    bandar_cnt = 0
    tss_cnt = 0

    f_lat, f_lon, f_rad = CONGESTION_HUBS["fujairah"]
    b_lat, b_lon, b_rad = CONGESTION_HUBS["bandar_abbas"]

    for v in loitering:
        if is_in_tss_lane(v.lat, v.lon):
            tss_cnt += 1
        elif haversine_nm(v.lat, v.lon, f_lat, f_lon) <= f_rad:
            fujairah_cnt += 1
        elif haversine_nm(v.lat, v.lon, b_lat, b_lon) <= b_rad:
            bandar_cnt += 1
        else:
            tss_cnt += 1

    moving_speeds = [v.speed_knots for v in vessels if v.speed_knots >= 3.0]
    avg_speed = float(np.mean(moving_speeds)) if moving_speeds else 11.5

    # Normalize loitering + speed drag into [0, 100]
    loiter_component = min(65.0, len(loitering) * 4.2 + tss_cnt * 2.5)
    speed_drag = max(0.0, (12.2 - avg_speed) * 9.5)
    live_index = max(0.0, min(100.0, loiter_component + speed_drag))

    ordered = sorted(daily_transits, key=lambda x: x.transit_date)
    if ordered:
        hist_loiter = np.array([d.loitering_count for d in ordered[-30:]], dtype=float)
        mean_l = float(np.mean(hist_loiter))
        std_l = float(np.std(hist_loiter)) or 1.0
        recent_l = float(np.mean(hist_loiter[-3:]))
        zscore = (recent_l - mean_l) / std_l
        # Blend latest daily congestion & live snapshot
        blended_index = 0.55 * live_index + 0.45 * float(ordered[-1].congestion_index)
    else:
        zscore = 0.0
        blended_index = live_index

    return CongestionMetricsResult(
        congestion_index=round(max(0.0, min(100.0, blended_index)), 1),
        loitering_vessels_count=len(loitering),
        fujairah_loitering=fujairah_cnt,
        bandar_abbas_loitering=bandar_cnt,
        tss_lane_loitering=tss_cnt,
        avg_transit_speed_knots=round(avg_speed, 2),
        congestion_zscore=round(zscore, 3),
    )

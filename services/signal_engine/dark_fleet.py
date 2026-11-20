"""Dark-Fleet / AIS Gap Spike Score inside the 25.5°N–27.0°N, 55.8°E–57.0°E Hormuz corridor."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from services.maritime_feed.base import AisGapRecord, DailyTransitPoint, VesselSnapshot
from services.signal_engine.geometry import is_in_dark_corridor


@dataclass
class DarkFleetMetricsResult:
    active_dark_vessels: int
    corridor_dark_vessels: int
    sanctioned_active_count: int
    dark_fleet_spike_score: float  # 0 to 100
    dark_fleet_zscore: float
    avg_gap_duration_hours: float


def compute_dark_fleet_score(
    vessels: Sequence[VesselSnapshot],
    ais_gaps: Sequence[AisGapRecord],
    daily_transits: Sequence[DailyTransitPoint],
) -> DarkFleetMetricsResult:
    """Count AIS-silent vessels inside 25.5°N–27.0°N, 55.8°E–57.0°E and compute spike score."""
    active_dark = [v for v in vessels if v.status == "ais_gap" or v.ais_gap_hours >= 3.0]
    corridor_dark = [v for v in active_dark if is_in_dark_corridor(v.lat, v.lon)]
    sanctioned_active = [v for v in vessels if v.is_sanctioned]

    active_gaps = [g for g in ais_gaps if g.end_time is None and g.in_corridor]
    avg_dur = (
        float(np.mean([g.duration_hours for g in active_gaps]))
        if active_gaps
        else (float(np.mean([v.ais_gap_hours for v in active_dark])) if active_dark else 0.0)
    )

    ordered = sorted(daily_transits, key=lambda x: x.transit_date)
    if ordered:
        series = np.array([d.ais_gap_count for d in ordered[-30:]], dtype=float)
        mean_g = float(np.mean(series))
        std_g = float(np.std(series)) or 1.0
        recent_g = float(np.mean(series[-3:]))
        zscore = (recent_g - mean_g) / std_g
    else:
        zscore = 0.0

    # Score combines corridor dark vessel count, sanctioned overlap, and rolling z-score
    raw_score = (
        len(corridor_dark) * 6.5
        + len(sanctioned_active) * 4.5
        + max(0.0, zscore) * 14.0
        + min(15.0, avg_dur * 0.7)
    )
    spike_score = max(0.0, min(100.0, raw_score))

    return DarkFleetMetricsResult(
        active_dark_vessels=len(active_dark),
        corridor_dark_vessels=len(corridor_dark),
        sanctioned_active_count=len(sanctioned_active),
        dark_fleet_spike_score=round(spike_score, 1),
        dark_fleet_zscore=round(zscore, 3),
        avg_gap_duration_hours=round(avg_dur, 1),
    )

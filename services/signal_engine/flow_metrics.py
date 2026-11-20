"""Net Outbound Laden Flow metrics (heading 090°-160°, draft > 12m; 7-day rolling vs. 30-day baseline)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from services.maritime_feed.base import DailyTransitPoint, VesselSnapshot
from services.signal_engine.geometry import is_outbound_laden


@dataclass
class FlowMetricsResult:
    live_outbound_laden_count: int
    live_outbound_barrels_mbbl: float
    rolling_7d_avg_count: float
    baseline_30d_avg_count: float
    rolling_7d_avg_mbbl: float
    baseline_30d_avg_mbbl: float
    flow_delta_7d_vs_30d_pct: float
    flow_zscore: float
    vlcc_share_pct: float


def compute_net_outbound_flow(
    vessels: Sequence[VesselSnapshot],
    daily_transits: Sequence[DailyTransitPoint],
) -> FlowMetricsResult:
    """Calculate live outbound laden count and 7-day rolling vs. 30-day baseline anomaly."""
    live_laden = [v for v in vessels if is_outbound_laden(v.heading, v.draft_m) or v.status == "outbound_laden"]
    live_count = len(live_laden)
    live_mbbl = round(sum(v.barrel_capacity for v in live_laden), 2)

    if not daily_transits:
        return FlowMetricsResult(
            live_outbound_laden_count=live_count,
            live_outbound_barrels_mbbl=live_mbbl,
            rolling_7d_avg_count=float(live_count),
            baseline_30d_avg_count=float(max(live_count, 1)),
            rolling_7d_avg_mbbl=live_mbbl,
            baseline_30d_avg_mbbl=max(live_mbbl, 1.0),
            flow_delta_7d_vs_30d_pct=0.0,
            flow_zscore=0.0,
            vlcc_share_pct=0.0,
        )

    ordered = sorted(daily_transits, key=lambda x: x.transit_date)
    counts = np.array([d.outbound_laden_count for d in ordered], dtype=float)
    mbbls = np.array([d.outbound_barrels_mbbl for d in ordered], dtype=float)

    window_7 = counts[-7:] if len(counts) >= 7 else counts
    window_30 = counts[-30:] if len(counts) >= 30 else counts
    mbbl_7 = mbbls[-7:] if len(mbbls) >= 7 else mbbls
    mbbl_30 = mbbls[-30:] if len(mbbls) >= 30 else mbbls

    avg_7 = float(np.mean(window_7))
    avg_30 = float(np.mean(window_30))
    std_30 = float(np.std(window_30)) or 1.0

    avg_mbbl_7 = float(np.mean(mbbl_7))
    avg_mbbl_30 = float(np.mean(mbbl_30))

    delta_pct = ((avg_7 - avg_30) / max(avg_30, 1e-6)) * 100.0
    zscore = (avg_7 - avg_30) / std_30

    recent_vlcc = sum(d.vlcc_count for d in ordered[-7:])
    recent_total = max(1, sum(d.outbound_laden_count for d in ordered[-7:]))
    vlcc_share = (recent_vlcc / recent_total) * 100.0

    return FlowMetricsResult(
        live_outbound_laden_count=live_count,
        live_outbound_barrels_mbbl=live_mbbl,
        rolling_7d_avg_count=round(avg_7, 2),
        baseline_30d_avg_count=round(avg_30, 2),
        rolling_7d_avg_mbbl=round(avg_mbbl_7, 2),
        baseline_30d_avg_mbbl=round(avg_mbbl_30, 2),
        flow_delta_7d_vs_30d_pct=round(delta_pct, 2),
        flow_zscore=round(zscore, 3),
        vlcc_share_pct=round(vlcc_share, 1),
    )

"""Fetches live HormuzFlow maritime + crude oil feeds and exports docs/data/live_snapshot.json for GitHub Pages."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from services.maritime_feed import MaritimeFeedManager
from services.market_feed import MarketFeedManager
from services.signal_engine import run_signal_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("build_live_pages")

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT_DIR / "docs" / "data" / "live_snapshot.json"


async def build_snapshot() -> dict:
    maritime_mgr = MaritimeFeedManager(
        feed_mode="auto",
        straits_live_api_key=os.getenv("STRAITS_LIVE_API_KEY", ""),
        datalastic_api_key=os.getenv("DATALASTIC_API_KEY", ""),
        marinetraffic_api_key=os.getenv("MARINETRAFFIC_API_KEY", ""),
        aisstream_api_key=os.getenv("AISSTREAM_API_KEY", ""),
    )
    market_mgr = MarketFeedManager(
        feed_mode="auto",
        alphavantage_api_key=os.getenv("ALPHAVANTAGE_API_KEY", ""),
    )

    maritime_payload, market_map = await asyncio.gather(
        maritime_mgr.fetch_all(days=45),
        market_mgr.fetch_all(days=45),
    )

    brent_daily = market_map[("BZ=F", "1d")]
    wti_daily = market_map[("CL=F", "1d")]

    sig = run_signal_engine(
        vessels=maritime_payload.vessels,
        ais_gaps=maritime_payload.ais_gaps,
        daily_transits=maritime_payload.daily_transits,
        brent_candles=brent_daily,
        wti_candles=wti_daily,
    )

    def _quote_stats(candles):
        latest = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else latest
        chg = round(latest.close - prev.close, 2)
        chg_pct = round((chg / max(prev.close, 1e-6)) * 100.0, 2)
        return latest.close, chg, chg_pct, latest.source

    bp, bc, bcp, oil_src = _quote_stats(brent_daily)
    wp, wc, wcp, _ = _quote_stats(wti_daily)

    vessel_src = maritime_payload.vessels[0].source if maritime_payload.vessels else "hormuz_simulator"
    transit_src = maritime_payload.daily_transits[-1].source if maritime_payload.daily_transits else "hormuz_simulator"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    payload = {
        "meta": {
            "updated_at": now_iso,
            "oil_source": oil_src,
            "transit_source": transit_src,
            "vessel_source": vessel_src,
            "adapters": [
                {"name": h.name, "category": h.category, "status": h.status, "message": h.message}
                for h in (maritime_mgr.get_health() + market_mgr.get_health())
            ],
        },
        "s": {
            "bp": bp,
            "bc": bc,
            "bcp": bcp,
            "wp": wp,
            "wc": wc,
            "wcp": wcp,
            "out24": sig.flow_metrics.live_outbound_laden_count,
            "mbbl24": sig.flow_metrics.live_outbound_barrels_mbbl,
            "fd7": sig.flow_metrics.flow_delta_7d_vs_30d_pct,
            "r7": sig.flow_metrics.rolling_7d_avg_count,
            "b30": sig.flow_metrics.baseline_30d_avg_count,
            "b30m": sig.flow_metrics.baseline_30d_avg_mbbl,
            "fz": sig.flow_metrics.flow_zscore,
            "dark": sig.dark_fleet_metrics.active_dark_vessels,
            "cdark": sig.dark_fleet_metrics.corridor_dark_vessels,
            "sanc": sig.dark_fleet_metrics.sanctioned_active_count,
            "cong": sig.congestion_metrics.congestion_index,
            "loit": sig.congestion_metrics.loitering_vessels_count,
            "avgSpd": sig.congestion_metrics.avg_transit_speed_knots,
            "dSpike": sig.dark_fleet_metrics.dark_fleet_spike_score,
            "shock": sig.supply_shock_score,
            "bias": sig.brent_bias,
            "p72b": sig.predicted_72h_brent_pct,
            "ciL": sig.confidence_low_pct,
            "ciH": sig.confidence_high_pct,
            "acc": sig.backtest_accuracy_pct,
            "sharpe": sig.signal_sharpe_estimate,
            "nbt": sig.backtest_sample_size,
        },
        "lags": [
            [x.lag_days, x.brent_corr, x.wti_corr, x.brent_up_prob_pct, x.wti_up_prob_pct]
            for x in sig.lag_correlations
        ],
        "divs": [
            [
                z.start_date,
                z.end_date,
                z.label,
                z.flow_drop_pct,
                z.subsequent_brent_move_pct,
                z.peak_shock_score,
            ]
            for z in sig.divergence_zones
        ],
        "bt": [
            [b.date[5:], b.predicted_3d_return_pct, b.actual_3d_return_pct, 1 if b.hit else 0]
            for b in sig.backtest_series[-20:]
        ],
        "ds": [
            [x.date, x.supply_shock_score, x.outbound_laden_count, x.outbound_7d_ma, x.outbound_barrels_mbbl]
            for x in sig.daily_signals
        ],
        "bz": [[c.timestamp.strftime("%Y-%m-%d"), c.open, c.high, c.low, c.close] for c in brent_daily[-45:]],
        "cl": [[c.timestamp.strftime("%Y-%m-%d"), c.open, c.high, c.low, c.close] for c in wti_daily[-45:]],
        "v": [
            [
                v.mmsi,
                v.imo,
                v.name,
                v.vessel_class,
                v.flag,
                round(v.lat, 3),
                round(v.lon, 3),
                v.speed_knots,
                round(v.heading, 0),
                v.draft_m,
                v.destination,
                v.status,
                1 if v.is_sanctioned else 0,
                v.dwt,
                v.barrel_capacity,
                v.ais_gap_hours,
            ]
            for v in maritime_payload.vessels[:120]
        ],
        "g": [
            [
                g.vessel_mmsi,
                g.vessel_name,
                g.vessel_class,
                g.severity,
                g.duration_hours,
                round(g.last_lat, 3),
                round(g.last_lon, 3),
                1 if g.is_sanctioned else 0,
                1 if g.end_time is None else 0,
                g.start_time.strftime("%Y-%m-%d %H:%M"),
            ]
            for g in maritime_payload.ais_gaps[:20]
        ],
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    logger.info(
        "Wrote %s | Oil=%s ($%.2f / $%.2f) | Transits=%s (%d days) | Vessels=%s (%d) | Shock=%+.1f (%s)",
        OUT_FILE,
        oil_src,
        bp,
        wp,
        transit_src,
        len(sig.daily_signals),
        vessel_src,
        len(maritime_payload.vessels),
        sig.supply_shock_score,
        sig.brent_bias,
    )
    return payload


if __name__ == "__main__":
    asyncio.run(build_snapshot())

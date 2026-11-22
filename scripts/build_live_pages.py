"""
Fetches live HormuzFlow maritime + multi-asset crude/tanker market feeds,
runs the 2-year walk-forward trade backtester, advances the automated paper-trading
ledger (docs/data/paper_trades.json), dispatches optional Discord/Telegram alerts,
and exports docs/data/live_snapshot.json for GitHub Pages.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from services.alerts import dispatch_webhook_alerts
from services.maritime_feed import MaritimeFeedManager
from services.maritime_feed.hormuz_now import HormuzNowAdapter
from services.maritime_feed.imf_portwatch import ImfPortWatchAdapter
from services.maritime_feed.simulator import HormuzSimulator
from services.market_feed import MarketFeedManager
from services.market_feed.equities import fetch_tradable_universe
from services.signal_engine import run_signal_engine
from services.signal_engine.backtester import backtest_to_dict, run_walk_forward_backtest
from services.signal_engine.paper_trader import (
    load_paper_ledger,
    save_paper_ledger,
    step_paper_portfolio,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("build_live_pages")

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT_DIR / "docs" / "data" / "live_snapshot.json"
PAPER_FILE = ROOT_DIR / "docs" / "data" / "paper_trades.json"


async def build_snapshot() -> dict:
    feed_mode = os.getenv("FEED_MODE", "auto")
    maritime_mgr = MaritimeFeedManager(
        feed_mode=feed_mode,  # type: ignore[arg-type]
        straits_live_api_key=os.getenv("STRAITS_LIVE_API_KEY", ""),
        datalastic_api_key=os.getenv("DATALASTIC_API_KEY", ""),
        marinetraffic_api_key=os.getenv("MARINETRAFFIC_API_KEY", ""),
        aisstream_api_key=os.getenv("AISSTREAM_API_KEY", ""),
    )
    market_mgr = MarketFeedManager(
        feed_mode=feed_mode,  # type: ignore[arg-type]
        alphavantage_api_key=os.getenv("ALPHAVANTAGE_API_KEY", ""),
    )
    hormuz_adapter = HormuzNowAdapter()
    imf_adapter = ImfPortWatchAdapter()

    # Fetch short-term live feeds, 2-year rich Hormuz context, and 2-year tradable ETF/tanker universe concurrently
    maritime_payload, market_map, rich_ctx, equity_universe = await asyncio.gather(
        maritime_mgr.fetch_all(days=45),
        market_mgr.fetch_all(days=45),
        hormuz_adapter.fetch_rich_context(days=730),
        fetch_tradable_universe(period="2y", feed_mode=feed_mode),  # type: ignore[arg-type]
    )

    # Ensure we have deep multi-year transit history for the 2-year walk-forward backtester
    history_transits = rich_ctx.get("history_transits") or []
    history_source = "hormuz_now+imf_portwatch" if len(history_transits) >= 120 else ""
    if len(history_transits) < 120:
        try:
            imf_2y = await imf_adapter.fetch(days=730)
            if len(imf_2y.daily_transits) > len(history_transits):
                history_transits = imf_2y.daily_transits
                history_source = "imf_portwatch"
        except Exception:
            pass
    if len(history_transits) < 120:
        sim_2y = HormuzSimulator().generate_sync(days=540)
        history_transits = sim_2y.daily_transits
        history_source = "hormuz_simulator_2y"

    brent_daily = market_map[("BZ=F", "1d")]
    wti_daily = market_map[("CL=F", "1d")]

    sig = run_signal_engine(
        vessels=maritime_payload.vessels,
        ais_gaps=maritime_payload.ais_gaps,
        daily_transits=maritime_payload.daily_transits,
        brent_candles=brent_daily,
        wti_candles=wti_daily,
    )

    waiting_total = int(rich_ctx.get("waiting_gulf", 0)) + int(rich_ctx.get("waiting_oman", 0))
    wf_result = run_walk_forward_backtest(
        asset_histories=equity_universe,
        transits=history_transits,
        live_shock_override=sig.supply_shock_score,
        live_flow_z_override=sig.flow_metrics.flow_zscore,
        live_cong_z_override=sig.congestion_metrics.congestion_zscore,
        waiting_queue_total=waiting_total,
    )

    # Advance automated Balanced Swing Desk paper-trading ledger
    ledger = load_paper_ledger(PAPER_FILE)
    ledger, new_alerts = step_paper_portfolio(
        ledger=ledger,
        live_tickets=wf_result.live_tickets,
        supply_shock_score=sig.supply_shock_score,
        brent_bias=sig.brent_bias,
        waiting_queue_total=waiting_total,
    )
    save_paper_ledger(PAPER_FILE, ledger)

    def _quote_stats(candles):
        latest = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else latest
        chg = round(latest.close - prev.close, 2)
        chg_pct = round((chg / max(prev.close, 1e-6)) * 100.0, 2)
        return latest.close, chg, chg_pct, latest.source

    bp, bc, bcp, oil_src = _quote_stats(brent_daily)
    wp, wc, wcp, _ = _quote_stats(wti_daily)

    # Dispatch optional Discord/Telegram alerts on high-conviction events
    alert_delivery = await dispatch_webhook_alerts(
        alerts=new_alerts,
        summary={"bp": bp, "wp": wp, "shock": sig.supply_shock_score, "bias": sig.brent_bias},
    )

    vessel_src = maritime_payload.vessels[0].source if maritime_payload.vessels else "hormuz_simulator"
    transit_src = maritime_payload.daily_transits[-1].source if maritime_payload.daily_transits else "hormuz_simulator"
    equity_src = equity_universe["BNO"].source if "BNO" in equity_universe else "market_simulator"
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    ais_dark_count = max(sig.dark_fleet_metrics.active_dark_vessels, int(rich_ctx.get("ais_silent_count", 0)))

    payload = {
        "meta": {
            "updated_at": now_iso,
            "oil_source": oil_src,
            "equity_source": equity_src,
            "transit_source": transit_src,
            "history_source": history_source,
            "history_days": len(history_transits),
            "vessel_source": vessel_src,
            "alert_delivery": alert_delivery,
            "adapters": [
                {"name": h.name, "category": h.category, "status": h.status, "message": h.message}
                for h in (maritime_mgr.get_health() + market_mgr.get_health())
            ],
        },
        "context": {
            "waiting_gulf": int(rich_ctx.get("waiting_gulf", 0)),
            "waiting_oman": int(rich_ctx.get("waiting_oman", 0)),
            "waiting_total": waiting_total,
            "fleet_total": int(rich_ctx.get("fleet_total", 0)),
            "fleet_tankers": int(rich_ctx.get("fleet_tankers", 0)),
            "gulf_export_pct_normal": float(rich_ctx.get("gulf_export_pct_normal", 100.0)),
            "ais_silent_count": int(rich_ctx.get("ais_silent_count", 0)),
            "status_level": rich_ctx.get("status_level", "unknown"),
            "status_pct_normal": rich_ctx.get("status_pct_normal"),
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
            "dark": ais_dark_count,
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
        "walk_forward": backtest_to_dict(wf_result),
        "paper_ledger": ledger,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    logger.info(
        "Wrote %s | Oil=%s ($%.2f / $%.2f) | History=%s (%dd) | 2Y WF Return=%+.1f%% (BNO %+.1f%%, Sharpe %.2f, WR %.1f%%, %d trades) | Paper Eq=$%.2f (%d open)",
        OUT_FILE,
        oil_src,
        bp,
        wp,
        history_source,
        len(history_transits),
        wf_result.total_return_pct,
        wf_result.bno_benchmark_return_pct,
        wf_result.sharpe_ratio,
        wf_result.win_rate_pct,
        wf_result.total_trades,
        ledger["equity"],
        len(ledger["open_positions"]),
    )
    return payload


if __name__ == "__main__":
    asyncio.run(build_snapshot())

"""REST API routes for dashboard KPIs, vessels, market candles, quantitative signals, stress-test, and adapters."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import (
    BacktestPointSchema,
    CandlesResponse,
    DailySignalSchema,
    DashboardSummaryResponse,
    DivergenceZoneSchema,
    FeedModeUpdateRequest,
    LagCorrelationSchema,
    MarketQuote,
    SignalsOverviewResponse,
    StressProjectionDaySchema,
    StressTestRequest,
    StressTestResponse,
    VesselDetailResponse,
)
from backend.state import data_service
from services.maritime_feed.base import AdapterHealth, AisGapRecord, VesselSnapshot
from services.market_feed.base import CandleInterval, OilSymbol
from services.signal_engine.geometry import (
    is_congestion_loitering,
    is_in_dark_corridor,
    is_in_tss_lane,
)
from services.signal_engine.stress_test import run_stress_test

router = APIRouter(prefix="/api", tags=["HormuzFlow"])


def _build_quote(symbol: OilSymbol, name: str) -> MarketQuote:
    candles = data_service.get_candles_from_db(symbol, "1d")
    if not candles:
        return MarketQuote(
            symbol=symbol,
            name=name,
            price=80.0 if symbol == "BZ=F" else 76.0,
            change_24h=0.0,
            change_24h_pct=0.0,
            high_24h=80.5,
            low_24h=79.5,
            source="fallback",
            updated_at=datetime.now(timezone.utc),
        )
    latest = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else latest
    chg = round(latest.close - prev.close, 2)
    chg_pct = round((chg / max(prev.close, 1e-6)) * 100.0, 2)
    return MarketQuote(
        symbol=symbol,
        name=name,
        price=latest.close,
        change_24h=chg,
        change_24h_pct=chg_pct,
        high_24h=latest.high,
        low_24h=latest.low,
        source=latest.source,
        updated_at=latest.timestamp,
    )


@router.get("/dashboard/summary", response_model=DashboardSummaryResponse)
async def get_dashboard_summary() -> DashboardSummaryResponse:
    sig = await data_service.get_signal()
    brent_q = _build_quote("BZ=F", "Brent Crude")
    wti_q = _build_quote("CL=F", "WTI Crude")

    return DashboardSummaryResponse(
        brent=brent_q,
        wti=wti_q,
        outbound_laden_24h=sig.flow_metrics.live_outbound_laden_count,
        outbound_barrels_24h_mbbl=sig.flow_metrics.live_outbound_barrels_mbbl,
        flow_delta_7d_pct=sig.flow_metrics.flow_delta_7d_vs_30d_pct,
        rolling_7d_avg_count=sig.flow_metrics.rolling_7d_avg_count,
        baseline_30d_avg_count=sig.flow_metrics.baseline_30d_avg_count,
        active_ais_dark_vessels=sig.dark_fleet_metrics.active_dark_vessels,
        corridor_dark_vessels=sig.dark_fleet_metrics.corridor_dark_vessels,
        sanctioned_active_count=sig.dark_fleet_metrics.sanctioned_active_count,
        congestion_index=sig.congestion_metrics.congestion_index,
        loitering_vessels_count=sig.congestion_metrics.loitering_vessels_count,
        supply_shock_score=sig.supply_shock_score,
        brent_bias=sig.brent_bias,
        wti_bias=sig.wti_bias,
        predicted_24h_brent_pct=sig.predicted_24h_brent_pct,
        predicted_72h_brent_pct=sig.predicted_72h_brent_pct,
        predicted_24h_wti_pct=sig.predicted_24h_wti_pct,
        predicted_72h_wti_pct=sig.predicted_72h_wti_pct,
        confidence_low_pct=sig.confidence_low_pct,
        confidence_high_pct=sig.confidence_high_pct,
        backtest_accuracy_pct=sig.backtest_accuracy_pct,
        feed_mode=data_service.feed_mode,
        maritime_source=data_service.maritime_source,
        market_source=data_service.market_source,
        last_refreshed=data_service.last_refreshed,
        adapters=data_service.get_all_adapter_health(),
    )


@router.get("/vessels", response_model=list[VesselSnapshot])
async def list_vessels(
    status: Optional[str] = Query(default=None),
    vessel_class: Optional[str] = Query(default=None),
) -> list[VesselSnapshot]:
    await data_service.get_signal()
    return data_service.get_vessels_from_db(status=status, vessel_class=vessel_class)


@router.get("/vessels/{mmsi}", response_model=VesselDetailResponse)
async def get_vessel_detail(mmsi: str) -> VesselDetailResponse:
    await data_service.get_signal()
    vessels = data_service.get_vessels_from_db()
    target = next((v for v in vessels if v.mmsi == mmsi), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"Vessel MMSI {mmsi} not found")
    gaps = data_service.get_ais_gaps_from_db(mmsi=mmsi)
    return VesselDetailResponse(
        vessel=target,
        in_dark_corridor=is_in_dark_corridor(target.lat, target.lon),
        in_tss_lane=is_in_tss_lane(target.lat, target.lon),
        is_congestion_loitering=is_congestion_loitering(target.lat, target.lon, target.speed_knots),
        ais_gap_history=gaps,
    )


@router.get("/ais-gaps", response_model=list[AisGapRecord])
async def list_ais_gaps() -> list[AisGapRecord]:
    await data_service.get_signal()
    return data_service.get_ais_gaps_from_db()


@router.get("/market/candles", response_model=CandlesResponse)
async def get_market_candles(
    symbol: OilSymbol = Query(default="BZ=F"),
    interval: CandleInterval = Query(default="1d"),
) -> CandlesResponse:
    sig = await data_service.get_signal()
    candles = data_service.get_candles_from_db(symbol, interval)
    source = candles[-1].source if candles else data_service.market_source
    return CandlesResponse(
        symbol=symbol,
        interval=interval,
        source=source,
        candles=candles,
        daily_signals=[DailySignalSchema(**asdict(p)) for p in sig.daily_signals],
        divergence_zones=[DivergenceZoneSchema(**asdict(z)) for z in sig.divergence_zones],
    )


@router.get("/signals/overview", response_model=SignalsOverviewResponse)
async def get_signals_overview() -> SignalsOverviewResponse:
    sig = await data_service.get_signal()
    return SignalsOverviewResponse(
        supply_shock_score=sig.supply_shock_score,
        brent_bias=sig.brent_bias,
        wti_bias=sig.wti_bias,
        predicted_24h_brent_pct=sig.predicted_24h_brent_pct,
        predicted_72h_brent_pct=sig.predicted_72h_brent_pct,
        predicted_24h_wti_pct=sig.predicted_24h_wti_pct,
        predicted_72h_wti_pct=sig.predicted_72h_wti_pct,
        confidence_low_pct=sig.confidence_low_pct,
        confidence_high_pct=sig.confidence_high_pct,
        backtest_accuracy_pct=sig.backtest_accuracy_pct,
        backtest_sample_size=sig.backtest_sample_size,
        signal_sharpe_estimate=sig.signal_sharpe_estimate,
        flow_metrics=asdict(sig.flow_metrics),
        congestion_metrics=asdict(sig.congestion_metrics),
        dark_fleet_metrics=asdict(sig.dark_fleet_metrics),
        lag_correlations=[LagCorrelationSchema(**asdict(lc)) for lc in sig.lag_correlations],
        divergence_zones=[DivergenceZoneSchema(**asdict(dz)) for dz in sig.divergence_zones],
        backtest_series=[BacktestPointSchema(**asdict(bp)) for bp in sig.backtest_series],
        daily_signals=[DailySignalSchema(**asdict(ds)) for ds in sig.daily_signals],
    )


@router.post("/simulation/stress-test", response_model=StressTestResponse)
async def simulate_stress_test(req: StressTestRequest) -> StressTestResponse:
    sig = await data_service.get_signal()
    brent_q = _build_quote("BZ=F", "Brent Crude")
    wti_q = _build_quote("CL=F", "WTI Crude")
    res = run_stress_test(
        brent_spot=brent_q.price,
        wti_spot=wti_q.price,
        current_shock_score=sig.supply_shock_score,
        baseline_outbound_mbbl=sig.flow_metrics.baseline_30d_avg_mbbl,
        vlcc_drop_pct=req.vlcc_drop_pct,
        ais_spoofing_multiplier=req.ais_spoofing_multiplier,
        congestion_surge_pct=req.congestion_surge_pct,
        duration_days=req.duration_days,
    )
    return StressTestResponse(
        vlcc_drop_pct=res.vlcc_drop_pct,
        ais_spoofing_multiplier=res.ais_spoofing_multiplier,
        congestion_surge_pct=res.congestion_surge_pct,
        duration_days=res.duration_days,
        projected_supply_shock_score=res.projected_supply_shock_score,
        disrupted_mbbl_per_day=res.disrupted_mbbl_per_day,
        brent_base_price=res.brent_base_price,
        brent_projected_price=res.brent_projected_price,
        brent_delta_usd=res.brent_delta_usd,
        brent_delta_pct=res.brent_delta_pct,
        wti_base_price=res.wti_base_price,
        wti_projected_price=res.wti_projected_price,
        wti_delta_usd=res.wti_delta_usd,
        wti_delta_pct=res.wti_delta_pct,
        risk_regime=res.risk_regime,
        projection_curve=[StressProjectionDaySchema(**asdict(d)) for d in res.projection_curve],
    )


@router.get("/adapters/status", response_model=list[AdapterHealth])
async def get_adapter_status() -> list[AdapterHealth]:
    await data_service.get_signal()
    return data_service.get_all_adapter_health()


@router.post("/adapters/refresh", response_model=DashboardSummaryResponse)
async def refresh_feeds() -> DashboardSummaryResponse:
    await data_service.ingest_and_recompute()
    return await get_dashboard_summary()


@router.post("/adapters/mode", response_model=DashboardSummaryResponse)
async def switch_feed_mode(req: FeedModeUpdateRequest) -> DashboardSummaryResponse:
    data_service.set_feed_mode(req.feed_mode)
    await data_service.ingest_and_recompute()
    return await get_dashboard_summary()

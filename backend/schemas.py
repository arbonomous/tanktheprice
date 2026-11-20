"""Pydantic request & response schemas for HormuzFlow REST API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from services.maritime_feed.base import AdapterHealth, AisGapRecord, VesselSnapshot
from services.market_feed.base import OilCandle


class MarketQuote(BaseModel):
    symbol: Literal["BZ=F", "CL=F"]
    name: str
    price: float
    change_24h: float
    change_24h_pct: float
    high_24h: float
    low_24h: float
    source: str
    updated_at: datetime


class DashboardSummaryResponse(BaseModel):
    brent: MarketQuote
    wti: MarketQuote
    outbound_laden_24h: int
    outbound_barrels_24h_mbbl: float
    flow_delta_7d_pct: float
    rolling_7d_avg_count: float
    baseline_30d_avg_count: float
    active_ais_dark_vessels: int
    corridor_dark_vessels: int
    sanctioned_active_count: int
    congestion_index: float
    loitering_vessels_count: int
    supply_shock_score: float
    brent_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    wti_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    predicted_24h_brent_pct: float
    predicted_72h_brent_pct: float
    predicted_24h_wti_pct: float
    predicted_72h_wti_pct: float
    confidence_low_pct: float
    confidence_high_pct: float
    backtest_accuracy_pct: float
    feed_mode: str
    maritime_source: str
    market_source: str
    last_refreshed: datetime
    adapters: list[AdapterHealth]


class VesselDetailResponse(BaseModel):
    vessel: VesselSnapshot
    in_dark_corridor: bool
    in_tss_lane: bool
    is_congestion_loitering: bool
    ais_gap_history: list[AisGapRecord]


class LagCorrelationSchema(BaseModel):
    lag_days: int
    brent_corr: float
    wti_corr: float
    brent_up_prob_pct: float
    wti_up_prob_pct: float


class DivergenceZoneSchema(BaseModel):
    start_date: str
    end_date: str
    label: str
    flow_drop_pct: float
    subsequent_brent_move_pct: float
    subsequent_wti_move_pct: float
    peak_shock_score: float


class BacktestPointSchema(BaseModel):
    date: str
    shock_score: float
    predicted_3d_return_pct: float
    actual_3d_return_pct: float
    hit: bool


class DailySignalSchema(BaseModel):
    date: str
    supply_shock_score: float
    outbound_laden_count: int
    outbound_7d_ma: float
    outbound_barrels_mbbl: float
    congestion_index: float
    ais_gap_count: int
    brent_close: Optional[float] = None
    wti_close: Optional[float] = None


class SignalsOverviewResponse(BaseModel):
    supply_shock_score: float
    brent_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    wti_bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    predicted_24h_brent_pct: float
    predicted_72h_brent_pct: float
    predicted_24h_wti_pct: float
    predicted_72h_wti_pct: float
    confidence_low_pct: float
    confidence_high_pct: float
    backtest_accuracy_pct: float
    backtest_sample_size: int
    signal_sharpe_estimate: float
    flow_metrics: dict
    congestion_metrics: dict
    dark_fleet_metrics: dict
    lag_correlations: list[LagCorrelationSchema]
    divergence_zones: list[DivergenceZoneSchema]
    backtest_series: list[BacktestPointSchema]
    daily_signals: list[DailySignalSchema]


class StressTestRequest(BaseModel):
    vlcc_drop_pct: float = Field(default=30.0, ge=0.0, le=80.0)
    ais_spoofing_multiplier: float = Field(default=2.0, ge=1.0, le=6.0)
    congestion_surge_pct: float = Field(default=25.0, ge=0.0, le=100.0)
    duration_days: int = Field(default=5, ge=1, le=21)


class StressProjectionDaySchema(BaseModel):
    day: int
    label: str
    baseline_brent: float
    stressed_brent: float
    baseline_wti: float
    stressed_wti: float


class StressTestResponse(BaseModel):
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
    projection_curve: list[StressProjectionDaySchema]


class CandlesResponse(BaseModel):
    symbol: Literal["BZ=F", "CL=F"]
    interval: Literal["1d", "1h"]
    source: str
    candles: list[OilCandle]
    daily_signals: list[DailySignalSchema]
    divergence_zones: list[DivergenceZoneSchema]


class FeedModeUpdateRequest(BaseModel):
    feed_mode: Literal["auto", "live", "simulator"]

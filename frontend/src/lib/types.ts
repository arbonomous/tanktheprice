export type VesselClass = "VLCC" | "Suezmax" | "Aframax" | "LR2" | "MR";
export type VesselStatus = "outbound_laden" | "inbound_ballast" | "loitering" | "ais_gap";
export type DirectionalBias = "BULLISH" | "BEARISH" | "NEUTRAL";
export type OilSymbol = "BZ=F" | "CL=F";

export interface AdapterHealth {
  name: string;
  category: "maritime" | "market";
  tier: "free_live" | "paid_ais" | "paid_market" | "simulator";
  configured: boolean;
  active: boolean;
  status: "LIVE" | "STANDBY_NO_KEY" | "FALLBACK_SIMULATOR" | "DEGRADED" | "DISABLED";
  message: string;
  last_checked: string;
}

export interface MarketQuote {
  symbol: OilSymbol;
  name: string;
  price: number;
  change_24h: number;
  change_24h_pct: number;
  high_24h: number;
  low_24h: number;
  source: string;
  updated_at: string;
}

export interface DashboardSummary {
  brent: MarketQuote;
  wti: MarketQuote;
  outbound_laden_24h: number;
  outbound_barrels_24h_mbbl: number;
  flow_delta_7d_pct: number;
  rolling_7d_avg_count: number;
  baseline_30d_avg_count: number;
  active_ais_dark_vessels: number;
  corridor_dark_vessels: number;
  sanctioned_active_count: number;
  congestion_index: number;
  loitering_vessels_count: number;
  supply_shock_score: number;
  brent_bias: DirectionalBias;
  wti_bias: DirectionalBias;
  predicted_24h_brent_pct: number;
  predicted_72h_brent_pct: number;
  predicted_24h_wti_pct: number;
  predicted_72h_wti_pct: number;
  confidence_low_pct: number;
  confidence_high_pct: number;
  backtest_accuracy_pct: number;
  feed_mode: "auto" | "live" | "simulator";
  maritime_source: string;
  market_source: string;
  last_refreshed: string;
  adapters: AdapterHealth[];
}

export interface VesselSnapshot {
  mmsi: string;
  imo: string;
  name: string;
  vessel_class: VesselClass;
  flag: string;
  lat: number;
  lon: number;
  speed_knots: number;
  heading: number;
  draft_m: number;
  destination: string;
  status: VesselStatus;
  is_sanctioned: boolean;
  dwt: number;
  barrel_capacity: number;
  ais_gap_hours: number;
  last_seen: string;
  source: string;
}

export interface AisGapRecord {
  vessel_mmsi: string;
  vessel_name: string;
  vessel_class: VesselClass;
  start_time: string;
  end_time: string | null;
  duration_hours: number;
  last_lat: number;
  last_lon: number;
  reappeared_lat: number | null;
  reappeared_lon: number | null;
  in_corridor: boolean;
  is_sanctioned: boolean;
  severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  source: string;
}

export interface VesselDetail {
  vessel: VesselSnapshot;
  in_dark_corridor: boolean;
  in_tss_lane: boolean;
  is_congestion_loitering: boolean;
  ais_gap_history: AisGapRecord[];
}

export interface OilCandle {
  symbol: OilSymbol;
  interval: "1d" | "1h";
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  source: string;
}

export interface DailySignalPoint {
  date: string;
  supply_shock_score: number;
  outbound_laden_count: number;
  outbound_7d_ma: number;
  outbound_barrels_mbbl: number;
  congestion_index: number;
  ais_gap_count: number;
  brent_close: number | null;
  wti_close: number | null;
}

export interface DivergenceZone {
  start_date: string;
  end_date: string;
  label: string;
  flow_drop_pct: number;
  subsequent_brent_move_pct: number;
  subsequent_wti_move_pct: number;
  peak_shock_score: number;
}

export interface LagCorrelation {
  lag_days: number;
  brent_corr: number;
  wti_corr: number;
  brent_up_prob_pct: number;
  wti_up_prob_pct: number;
}

export interface BacktestPoint {
  date: string;
  shock_score: number;
  predicted_3d_return_pct: number;
  actual_3d_return_pct: number;
  hit: boolean;
}

export interface SignalsOverview {
  supply_shock_score: number;
  brent_bias: DirectionalBias;
  wti_bias: DirectionalBias;
  predicted_24h_brent_pct: number;
  predicted_72h_brent_pct: number;
  predicted_24h_wti_pct: number;
  predicted_72h_wti_pct: number;
  confidence_low_pct: number;
  confidence_high_pct: number;
  backtest_accuracy_pct: number;
  backtest_sample_size: number;
  signal_sharpe_estimate: number;
  flow_metrics: {
    live_outbound_laden_count: number;
    live_outbound_barrels_mbbl: number;
    rolling_7d_avg_count: number;
    baseline_30d_avg_count: number;
    rolling_7d_avg_mbbl: number;
    baseline_30d_avg_mbbl: number;
    flow_delta_7d_vs_30d_pct: number;
    flow_zscore: number;
    vlcc_share_pct: number;
  };
  congestion_metrics: {
    congestion_index: number;
    loitering_vessels_count: number;
    fujairah_loitering: number;
    bandar_abbas_loitering: number;
    tss_lane_loitering: number;
    avg_transit_speed_knots: number;
    congestion_zscore: number;
  };
  dark_fleet_metrics: {
    active_dark_vessels: number;
    corridor_dark_vessels: number;
    sanctioned_active_count: number;
    dark_fleet_spike_score: number;
    dark_fleet_zscore: number;
    avg_gap_duration_hours: number;
  };
  lag_correlations: LagCorrelation[];
  divergence_zones: DivergenceZone[];
  backtest_series: BacktestPoint[];
  daily_signals: DailySignalPoint[];
}

export interface CandlesResponse {
  symbol: OilSymbol;
  interval: "1d" | "1h";
  source: string;
  candles: OilCandle[];
  daily_signals: DailySignalPoint[];
  divergence_zones: DivergenceZone[];
}

export interface StressTestPayload {
  vlcc_drop_pct: number;
  ais_spoofing_multiplier: number;
  congestion_surge_pct: number;
  duration_days: number;
}

export interface StressProjectionDay {
  day: number;
  label: string;
  baseline_brent: number;
  stressed_brent: number;
  baseline_wti: number;
  stressed_wti: number;
}

export interface StressTestResult {
  vlcc_drop_pct: number;
  ais_spoofing_multiplier: number;
  congestion_surge_pct: number;
  duration_days: number;
  projected_supply_shock_score: number;
  disrupted_mbbl_per_day: number;
  brent_base_price: number;
  brent_projected_price: number;
  brent_delta_usd: number;
  brent_delta_pct: number;
  wti_base_price: number;
  wti_projected_price: number;
  wti_delta_usd: number;
  wti_delta_pct: number;
  risk_regime: string;
  projection_curve: StressProjectionDay[];
}

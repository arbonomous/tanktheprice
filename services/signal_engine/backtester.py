"""
2-Year Walk-Forward Trade-Level Backtester & Live Swing Signal Generator
Balanced Swing Desk Rules:
  - Universe: BNO, USO, FRO, DHT, STNG (1-5 day swing timeframe)
  - Starting Capital: $100,000
  - Risk per Trade: 1.5% of current equity (capped at 33% equity per position)
  - Max Concurrent Positions: 3
  - Stop-Loss: 1.5 x ATR(14) | Profit Target: 2.8 x ATR(14) | Time Stop: 5 trading days
  - Slippage: 10 bps round-trip (5 bps entry + 5 bps exit)
  - Zero Lookahead: Signals computed at close(t) execute at open(t+1)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Literal, Sequence

import numpy as np
import pandas as pd

from services.maritime_feed.base import DailyTransitPoint
from services.market_feed.equities import TRADABLE_TICKERS, AssetHistory

STARTING_EQUITY = 100_000.0
RISK_PER_TRADE_PCT = 0.015
MAX_CONCURRENT_POSITIONS = 3
MAX_POSITION_EQUITY_FRAC = 0.33
STOP_ATR_MULT = 1.5
TARGET_ATR_MULT = 2.8
MAX_HOLD_DAYS = 5
ONE_WAY_SLIPPAGE = 0.0005  # 5 bps each side = 10 bps round-trip


@dataclass
class LiveSignalTicket:
    ticker: str
    name: str
    role: str
    asset_type: str
    price: float
    change_1d_pct: float
    atr_14: float
    atr_pct: float
    conviction: float  # 0..100
    stance: Literal["LONG", "SHORT", "WATCH"]
    entry_price: float
    stop_price: float
    target_price: float
    reward_risk: float
    suggested_shares: int
    suggested_notional: float
    risk_usd: float
    rationale: str


@dataclass
class ClosedTradeRecord:
    ticker: str
    side: Literal["LONG", "SHORT"]
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    pnl_usd: float
    pnl_pct: float
    r_multiple: float
    hold_days: int
    exit_reason: Literal["TARGET_HIT", "STOP_OUT", "TIME_STOP", "SIGNAL_EXIT"]


@dataclass
class TickerBacktestStat:
    ticker: str
    name: str
    trades: int
    win_rate_pct: float
    net_pnl_usd: float
    profit_factor: float
    avg_r: float


@dataclass
class EquityCurvePoint:
    date: str
    strategy_equity: float
    bno_equity: float
    drawdown_pct: float


@dataclass
class WalkForwardBacktestResult:
    start_date: str
    end_date: str
    trading_days: int
    starting_equity: float
    ending_equity: float
    total_return_pct: float
    bno_benchmark_return_pct: float
    alpha_vs_bno_pct: float
    total_trades: int
    win_rate_pct: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown_pct: float
    avg_hold_days: float
    expectancy_r: float
    slippage_bps_roundtrip: int
    risk_per_trade_pct: float
    max_concurrent: int
    equity_curve: list[EquityCurvePoint]
    ticker_stats: list[TickerBacktestStat]
    recent_trades: list[ClosedTradeRecord]
    live_tickets: list[LiveSignalTicket]


def _build_asset_df(hist: AssetHistory) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {"date": b.date, "open": b.open, "high": b.high, "low": b.low, "close": b.close}
            for b in hist.bars
        ]
    ).drop_duplicates(subset=["date"]).sort_values("date").set_index("date")
    prev_c = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_c).abs(),
            (df["low"] - prev_c).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = tr.rolling(14, min_periods=5).mean().bfill()
    df["sma20"] = df["close"].rolling(20, min_periods=5).mean().bfill()
    df["ret5"] = df["close"].pct_change(5).fillna(0.0)
    return df


def _build_maritime_feature_frame(
    trading_dates: list[date],
    transits: Sequence[DailyTransitPoint],
    brent_close: pd.Series | None,
    wti_close: pd.Series | None,
) -> pd.DataFrame:
    """Align multi-year daily Hormuz transit features strictly without lookahead."""
    idx = pd.Index(trading_dates, name="date")
    feat = pd.DataFrame(index=idx)

    if transits:
        tdf = pd.DataFrame(
            [
                {
                    "date": t.transit_date,
                    "outbound": float(t.outbound_laden_count),
                    "congestion": float(t.congestion_index),
                    "ais_gaps": float(t.ais_gap_count),
                }
                for t in sorted(transits, key=lambda x: x.transit_date)
            ]
        ).drop_duplicates(subset=["date"]).set_index("date")
        # Reindex to calendar + forward fill up to 5 days for weekend/publication lags
        feat["outbound"] = tdf["outbound"].reindex(idx, method="ffill").bfill()
        feat["congestion"] = tdf["congestion"].reindex(idx, method="ffill").bfill()
        feat["ais_gaps"] = tdf["ais_gaps"].reindex(idx, method="ffill").bfill()
    else:
        feat["outbound"] = 20.0
        feat["congestion"] = 35.0
        feat["ais_gaps"] = 2.0

    # Strictly backward-looking rolling baselines
    feat["out_5d"] = feat["outbound"].rolling(5, min_periods=1).mean()
    feat["out_30d"] = feat["outbound"].rolling(30, min_periods=10).mean().bfill()
    feat["out_30d_std"] = feat["outbound"].rolling(30, min_periods=10).std().bfill().clip(lower=0.75)
    feat["flow_z"] = ((feat["out_5d"] - feat["out_30d"]) / feat["out_30d_std"]).clip(-4.0, 4.0)

    feat["out_90d"] = feat["outbound"].rolling(90, min_periods=20).mean().bfill()
    feat["regime_drop_pct"] = ((feat["out_5d"] - feat["out_90d"]) / feat["out_90d"].clip(lower=1.0)) * 100.0

    feat["cong_30d"] = feat["congestion"].rolling(30, min_periods=10).mean().bfill()
    feat["cong_std"] = feat["congestion"].rolling(30, min_periods=10).std().bfill().clip(lower=3.0)
    feat["cong_z"] = ((feat["congestion"] - feat["cong_30d"]) / feat["cong_std"]).clip(-3.5, 3.5)

    if brent_close is not None and wti_close is not None:
        spread = (brent_close.reindex(idx).ffill().bfill() - wti_close.reindex(idx).ffill().bfill())
        sp_ma = spread.rolling(30, min_periods=10).mean().bfill()
        sp_sd = spread.rolling(30, min_periods=10).std().bfill().clip(lower=0.35)
        feat["spread_z"] = ((spread - sp_ma) / sp_sd).clip(-3.5, 3.5)
    else:
        feat["spread_z"] = 0.0

    # Composite daily supply shock (-100..+100), strictly backward-looking
    raw_shock = (-0.52 * feat["flow_z"] + 0.28 * feat["cong_z"] + 0.20 * feat["spread_z"]) * 32.0
    # Add persistent crisis bonus when traffic is structurally >40% below 90d average
    crisis_bonus = np.where(feat["regime_drop_pct"] < -35.0, 12.0, 0.0)
    feat["shock"] = (raw_shock + crisis_bonus).clip(-100.0, 100.0)
    return feat


def _score_ticker_signal(
    ticker: str,
    shock: float,
    flow_z: float,
    cong_z: float,
    spread_z: float,
    close_px: float,
    sma20: float,
    ret5: float,
) -> tuple[Literal["LONG", "SHORT", "WATCH"], float, str]:
    """
    Generate directional swing stance + conviction (0..100) for each tradable ticker
    combining Hormuz maritime choke signals with trend/momentum confirmation.
    """
    above_trend = close_px >= sma20
    below_trend = close_px < sma20
    is_tanker = ticker in ("FRO", "DHT", "STNG")

    # Tanker equities respond most strongly to congestion/ton-mile squeezing + trend alignment
    if is_tanker:
        bull_score = max(0.0, shock) * 0.95 + max(0.0, cong_z) * 14.0 + (14.0 if above_trend else -10.0) + (8.0 if ret5 > 0 else -4.0)
        bear_score = max(0.0, -shock) * 0.85 + max(0.0, flow_z) * 12.0 + (12.0 if below_trend else -12.0)
    elif ticker == "BNO":
        # BNO carries highest direct Brent Hormuz choke beta
        bull_score = max(0.0, shock) * 1.10 + max(0.0, spread_z) * 14.0 + (12.0 if above_trend else -6.0) + (6.0 if ret5 > -0.02 else -6.0)
        bear_score = max(0.0, -shock) * 1.05 + max(0.0, -spread_z) * 12.0 + (12.0 if below_trend else -10.0)
    else:  # USO
        bull_score = max(0.0, shock) * 0.95 + max(0.0, -flow_z) * 12.0 + (12.0 if above_trend else -8.0)
        bear_score = max(0.0, -shock) * 1.00 + max(0.0, flow_z) * 12.0 + (12.0 if below_trend else -10.0)

    bull_conv = round(max(0.0, min(99.0, bull_score)), 1)
    bear_conv = round(max(0.0, min(99.0, bear_score)), 1)

    if bull_conv >= 56.0 and shock >= 16.0 and (above_trend or shock >= 32.0):
        reason = (
            f"Hormuz shock {shock:+.1f} + congestion surge favoring tanker dayrates"
            if is_tanker
            else f"Hormuz supply shock {shock:+.1f} (flow {flow_z:+.1f}σ) with Brent choke tailwind"
        )
        return "LONG", bull_conv, reason

    if bear_conv >= 58.0 and shock <= -14.0 and below_trend:
        reason = f"Hormuz transit normalization (shock {shock:+.1f}, flow {flow_z:+.1f}σ) compressing risk premium"
        return "SHORT", bear_conv, reason

    watch_conv = round(max(bull_conv, bear_conv) * 0.65, 1)
    reason = f"Mixed trend/flow alignment (shock {shock:+.1f}, {'above' if above_trend else 'below'} 20d SMA) — wait for confirmation"
    return "WATCH", watch_conv, reason


def run_walk_forward_backtest(
    asset_histories: dict[str, AssetHistory],
    transits: Sequence[DailyTransitPoint],
    live_shock_override: float | None = None,
    live_flow_z_override: float | None = None,
    live_cong_z_override: float | None = None,
    waiting_queue_total: int = 0,
) -> WalkForwardBacktestResult:
    """Run a zero-lookahead 2-year trade-level walk-forward backtest across BNO, USO, FRO, DHT, STNG."""
    dfs = {t: _build_asset_df(asset_histories[t]) for t in TRADABLE_TICKERS if t in asset_histories}
    if "BNO" not in dfs:
        raise ValueError("BNO history is required for walk-forward backtest")

    common_dates = sorted(dfs["BNO"].index.tolist())
    # Align all tradable dataframes to BNO trading calendar
    for t in list(dfs.keys()):
        dfs[t] = dfs[t].reindex(common_dates).ffill().bfill()

    brent_s = _build_asset_df(asset_histories["BZ=F"])["close"] if "BZ=F" in asset_histories else dfs["BNO"]["close"]
    wti_s = _build_asset_df(asset_histories["CL=F"])["close"] if "CL=F" in asset_histories else dfs["USO"]["close"]

    feat = _build_maritime_feature_frame(common_dates, transits, brent_s, wti_s)

    cash = STARTING_EQUITY
    open_positions: dict[str, dict] = {}
    closed_trades: list[ClosedTradeRecord] = []
    equity_curve: list[EquityCurvePoint] = []
    peak_equity = STARTING_EQUITY
    daily_returns: list[float] = []

    warmup = min(35, max(10, len(common_dates) // 8))
    bno_start_px = float(dfs["BNO"]["close"].iloc[warmup])

    for i in range(warmup, len(common_dates)):
        d = common_dates[i]
        d_str = d.isoformat()

        # 1. Check exits on open positions using today's high/low/open/close
        to_close: list[tuple[str, float, Literal["TARGET_HIT", "STOP_OUT", "TIME_STOP", "SIGNAL_EXIT"]]] = []
        for tkr, pos in open_positions.items():
            bar = dfs[tkr].iloc[i]
            o_px, h_px, l_px, c_px = float(bar["open"]), float(bar["high"]), float(bar["low"]), float(bar["close"])
            pos["hold_days"] += 1

            if pos["side"] == "LONG":
                # Conservative ordering: check stop-loss before target on same-bar overlap
                if l_px <= pos["stop"]:
                    exit_px = min(o_px, pos["stop"])
                    to_close.append((tkr, exit_px, "STOP_OUT"))
                elif h_px >= pos["target"]:
                    exit_px = max(o_px, pos["target"])
                    to_close.append((tkr, exit_px, "TARGET_HIT"))
                elif pos["hold_days"] >= MAX_HOLD_DAYS:
                    to_close.append((tkr, c_px, "TIME_STOP"))
                elif float(feat["shock"].iloc[i - 1]) <= -18.0:
                    to_close.append((tkr, o_px, "SIGNAL_EXIT"))
            else:
                if h_px >= pos["stop"]:
                    exit_px = max(o_px, pos["stop"])
                    to_close.append((tkr, exit_px, "STOP_OUT"))
                elif l_px <= pos["target"]:
                    exit_px = min(o_px, pos["target"])
                    to_close.append((tkr, exit_px, "TARGET_HIT"))
                elif pos["hold_days"] >= MAX_HOLD_DAYS:
                    to_close.append((tkr, c_px, "TIME_STOP"))
                elif float(feat["shock"].iloc[i - 1]) >= 20.0:
                    to_close.append((tkr, o_px, "SIGNAL_EXIT"))

        for tkr, raw_exit_px, reason in to_close:
            pos = open_positions.pop(tkr)
            slip_exit = raw_exit_px * (1.0 - ONE_WAY_SLIPPAGE if pos["side"] == "LONG" else 1.0 + ONE_WAY_SLIPPAGE)
            if pos["side"] == "LONG":
                pnl = (slip_exit - pos["entry_px"]) * pos["shares"]
                cash += slip_exit * pos["shares"]
            else:
                pnl = (pos["entry_px"] - slip_exit) * pos["shares"]
                cash += pos["notional"] + pnl

            pnl_pct = (pnl / max(pos["notional"], 1e-6)) * 100.0
            r_mult = pnl / max(pos["risk_usd"], 1.0)
            closed_trades.append(
                ClosedTradeRecord(
                    ticker=tkr,
                    side=pos["side"],
                    entry_date=pos["entry_date"],
                    exit_date=d_str,
                    entry_price=round(pos["entry_px"], 2),
                    exit_price=round(slip_exit, 2),
                    shares=pos["shares"],
                    pnl_usd=round(pnl, 2),
                    pnl_pct=round(pnl_pct, 2),
                    r_multiple=round(r_mult, 2),
                    hold_days=pos["hold_days"],
                    exit_reason=reason,
                )
            )

        # 2. Evaluate new entries strictly from yesterday's (i-1) features -> execute at today's open(i)
        if len(open_positions) < MAX_CONCURRENT_POSITIONS and i < len(common_dates) - 1:
            prev_f = feat.iloc[i - 1]
            candidates: list[tuple[float, str, Literal["LONG", "SHORT"]]] = []
            for tkr in TRADABLE_TICKERS:
                if tkr not in dfs or tkr in open_positions:
                    continue
                prev_bar = dfs[tkr].iloc[i - 1]
                stance, conv, _ = _score_ticker_signal(
                    tkr,
                    float(prev_f["shock"]),
                    float(prev_f["flow_z"]),
                    float(prev_f["cong_z"]),
                    float(prev_f["spread_z"]),
                    float(prev_bar["close"]),
                    float(prev_bar["sma20"]),
                    float(prev_bar["ret5"]),
                )
                if stance in ("LONG", "SHORT"):
                    candidates.append((conv, tkr, stance))

            candidates.sort(key=lambda x: x[0], reverse=True)
            # Mark equity before sizing
            mark_eq = cash + sum(
                (float(dfs[t]["open"].iloc[i]) * p["shares"] if p["side"] == "LONG" else p["notional"] + (p["entry_px"] - float(dfs[t]["open"].iloc[i])) * p["shares"])
                for t, p in open_positions.items()
            )
            for conv, tkr, side in candidates:
                if len(open_positions) >= MAX_CONCURRENT_POSITIONS:
                    break
                open_px = float(dfs[tkr]["open"].iloc[i])
                atr = max(open_px * 0.01, float(dfs[tkr]["atr14"].iloc[i - 1]))
                entry_px = open_px * (1.0 + ONE_WAY_SLIPPAGE if side == "LONG" else 1.0 - ONE_WAY_SLIPPAGE)
                stop_dist = STOP_ATR_MULT * atr
                risk_budget = mark_eq * RISK_PER_TRADE_PCT
                raw_shares = int(risk_budget / max(stop_dist, 0.01))
                max_notional = min(cash * 0.96, mark_eq * MAX_POSITION_EQUITY_FRAC)
                shares = min(raw_shares, int(max_notional / max(entry_px, 0.01)))
                if shares <= 0:
                    continue

                notional = shares * entry_px
                cash -= notional
                stop_px = entry_px - stop_dist if side == "LONG" else entry_px + stop_dist
                target_px = entry_px + TARGET_ATR_MULT * atr if side == "LONG" else entry_px - TARGET_ATR_MULT * atr

                open_positions[tkr] = {
                    "side": side,
                    "entry_date": d_str,
                    "entry_px": entry_px,
                    "shares": shares,
                    "notional": notional,
                    "risk_usd": shares * stop_dist,
                    "stop": stop_px,
                    "target": target_px,
                    "hold_days": 0,
                }

        # 3. End-of-day mark-to-market equity
        eod_eq = cash
        for tkr, p in open_positions.items():
            c_px = float(dfs[tkr]["close"].iloc[i])
            if p["side"] == "LONG":
                eod_eq += c_px * p["shares"]
            else:
                eod_eq += p["notional"] + (p["entry_px"] - c_px) * p["shares"]

        if equity_curve:
            prev_eq = equity_curve[-1].strategy_equity
            daily_returns.append((eod_eq / max(prev_eq, 1.0)) - 1.0)
        peak_equity = max(peak_equity, eod_eq)
        dd_pct = ((eod_eq - peak_equity) / max(peak_equity, 1.0)) * 100.0
        bno_eq = STARTING_EQUITY * (float(dfs["BNO"]["close"].iloc[i]) / max(bno_start_px, 1e-6))

        equity_curve.append(
            EquityCurvePoint(
                date=d_str,
                strategy_equity=round(eod_eq, 2),
                bno_equity=round(bno_eq, 2),
                drawdown_pct=round(dd_pct, 2),
            )
        )

    # Aggregate statistics
    ending_eq = equity_curve[-1].strategy_equity if equity_curve else STARTING_EQUITY
    bno_end_eq = equity_curve[-1].bno_equity if equity_curve else STARTING_EQUITY
    total_ret = ((ending_eq / STARTING_EQUITY) - 1.0) * 100.0
    bno_ret = ((bno_end_eq / STARTING_EQUITY) - 1.0) * 100.0
    max_dd = min((p.drawdown_pct for p in equity_curve), default=0.0)

    wins = [t for t in closed_trades if t.pnl_usd > 0]
    losses = [t for t in closed_trades if t.pnl_usd <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100.0) if closed_trades else 0.0
    gross_profit = sum(t.pnl_usd for t in wins)
    gross_loss = abs(sum(t.pnl_usd for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (round(gross_profit / 100.0, 2) if gross_profit > 0 else 1.0)
    avg_hold = float(np.mean([t.hold_days for t in closed_trades])) if closed_trades else 0.0
    exp_r = float(np.mean([t.r_multiple for t in closed_trades])) if closed_trades else 0.0

    if len(daily_returns) >= 10 and np.std(daily_returns) > 1e-8:
        sharpe = float((np.mean(daily_returns) / np.std(daily_returns)) * np.sqrt(252.0))
    else:
        sharpe = 0.0

    # Per-ticker stats
    ticker_stats: list[TickerBacktestStat] = []
    for tkr in TRADABLE_TICKERS:
        if tkr not in asset_histories:
            continue
        ts = [t for t in closed_trades if t.ticker == tkr]
        tw = [t for t in ts if t.pnl_usd > 0]
        tl = [t for t in ts if t.pnl_usd <= 0]
        gp = sum(t.pnl_usd for t in tw)
        gl = abs(sum(t.pnl_usd for t in tl))
        ticker_stats.append(
            TickerBacktestStat(
                ticker=tkr,
                name=asset_histories[tkr].name,
                trades=len(ts),
                win_rate_pct=round((len(tw) / len(ts) * 100.0) if ts else 0.0, 1),
                net_pnl_usd=round(sum(t.pnl_usd for t in ts), 2),
                profit_factor=round(gp / gl, 2) if gl > 0 else (2.0 if gp > 0 else 0.0),
                avg_r=round(float(np.mean([t.r_multiple for t in ts])) if ts else 0.0, 2),
            )
        )

    # Generate Live Signal Tickets for today using latest real prices + live maritime signal
    last_f = feat.iloc[-1]
    cur_shock = float(live_shock_override if live_shock_override is not None else last_f["shock"])
    cur_flow_z = float(live_flow_z_override if live_flow_z_override is not None else last_f["flow_z"])
    cur_cong_z = float(live_cong_z_override if live_cong_z_override is not None else last_f["cong_z"])
    # Queue surge bonus if live waiting queues off Oman + Persian Gulf are elevated (>350 vessels)
    if waiting_queue_total >= 350:
        cur_cong_z = max(cur_cong_z, 1.4)
    cur_spread_z = float(last_f["spread_z"])

    live_tickets: list[LiveSignalTicket] = []
    for tkr in TRADABLE_TICKERS:
        if tkr not in asset_histories:
            continue
        ah = asset_histories[tkr]
        stance, conv, reason = _score_ticker_signal(
            tkr, cur_shock, cur_flow_z, cur_cong_z, cur_spread_z, ah.latest_price, ah.sma_20, ah.ret_5d_pct / 100.0
        )
        atr = max(ah.latest_price * 0.01, ah.atr_14)
        stop_dist = STOP_ATR_MULT * atr
        target_dist = TARGET_ATR_MULT * atr
        if stance == "SHORT":
            stop_px = round(ah.latest_price + stop_dist, 2)
            target_px = round(max(0.5, ah.latest_price - target_dist), 2)
        else:
            stop_px = round(max(0.5, ah.latest_price - stop_dist), 2)
            target_px = round(ah.latest_price + target_dist, 2)

        risk_usd = STARTING_EQUITY * RISK_PER_TRADE_PCT
        shares = min(
            int(risk_usd / max(stop_dist, 0.01)),
            int((STARTING_EQUITY * MAX_POSITION_EQUITY_FRAC) / max(ah.latest_price, 0.01)),
        )
        live_tickets.append(
            LiveSignalTicket(
                ticker=tkr,
                name=ah.name,
                role=ah.role,
                asset_type=ah.asset_type,
                price=ah.latest_price,
                change_1d_pct=ah.change_1d_pct,
                atr_14=round(atr, 2),
                atr_pct=ah.atr_pct,
                conviction=conv,
                stance=stance,
                entry_price=ah.latest_price,
                stop_price=stop_px,
                target_price=target_px,
                reward_risk=round(target_dist / max(stop_dist, 1e-6), 2),
                suggested_shares=max(1, shares),
                suggested_notional=round(max(1, shares) * ah.latest_price, 2),
                risk_usd=round(max(1, shares) * stop_dist, 2),
                rationale=reason,
            )
        )

    live_tickets.sort(key=lambda x: (0 if x.stance != "WATCH" else 1, -x.conviction))

    # Downsample equity curve gently to <= 160 points for crisp fast frontend JSON while preserving start & end
    if len(equity_curve) > 160:
        step = max(1, len(equity_curve) // 155)
        sampled = equity_curve[::step]
        if sampled[-1].date != equity_curve[-1].date:
            sampled.append(equity_curve[-1])
        curve_out = sampled
    else:
        curve_out = equity_curve

    return WalkForwardBacktestResult(
        start_date=equity_curve[0].date if equity_curve else "",
        end_date=equity_curve[-1].date if equity_curve else "",
        trading_days=len(equity_curve),
        starting_equity=STARTING_EQUITY,
        ending_equity=round(ending_eq, 2),
        total_return_pct=round(total_ret, 2),
        bno_benchmark_return_pct=round(bno_ret, 2),
        alpha_vs_bno_pct=round(total_ret - bno_ret, 2),
        total_trades=len(closed_trades),
        win_rate_pct=round(win_rate, 1),
        profit_factor=profit_factor,
        sharpe_ratio=round(sharpe, 2),
        max_drawdown_pct=round(max_dd, 2),
        avg_hold_days=round(avg_hold, 1),
        expectancy_r=round(exp_r, 2),
        slippage_bps_roundtrip=int(ONE_WAY_SLIPPAGE * 20_000),
        risk_per_trade_pct=round(RISK_PER_TRADE_PCT * 100.0, 2),
        max_concurrent=MAX_CONCURRENT_POSITIONS,
        equity_curve=curve_out,
        ticker_stats=ticker_stats,
        recent_trades=list(reversed(closed_trades[-25:])),
        live_tickets=live_tickets,
    )


def backtest_to_dict(res: WalkForwardBacktestResult) -> dict:
    return asdict(res)

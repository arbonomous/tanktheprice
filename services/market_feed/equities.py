"""Multi-asset crude ETF & tanker equity market data fetcher (BNO, USO, FRO, DHT, STNG + BZ=F, CL=F)."""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Literal

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

TRADABLE_TICKERS = ("BNO", "USO", "FRO", "DHT", "STNG")

TICKER_META: dict[str, dict[str, str]] = {
    "BNO": {"name": "US Brent Oil Fund ETF", "role": "Direct Seaborne Brent Beta", "asset_type": "ETF"},
    "USO": {"name": "US Oil Fund WTI ETF", "role": "US WTI Crude & Spread Leg", "asset_type": "ETF"},
    "FRO": {"name": "Frontline plc", "role": "VLCC & Suezmax Tanker Leader", "asset_type": "TANKER"},
    "DHT": {"name": "DHT Holdings", "role": "Pure-Play VLCC Fleet", "asset_type": "TANKER"},
    "STNG": {"name": "Scorpio Tankers", "role": "LR2 / Product Tanker Leader", "asset_type": "TANKER"},
}


@dataclass
class AssetBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass
class AssetHistory:
    symbol: str
    name: str
    role: str
    asset_type: str
    source: str
    bars: list[AssetBar]
    latest_price: float
    change_1d_pct: float
    atr_14: float
    atr_pct: float
    sma_20: float
    ret_5d_pct: float


def compute_atr_14(bars: list[AssetBar]) -> float:
    if len(bars) < 2:
        return round(bars[-1].close * 0.025, 4) if bars else 1.0
    trs: list[float] = []
    for i in range(1, len(bars)):
        h, l, prev_c = bars[i].high, bars[i].low, bars[i - 1].close
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
    window = trs[-14:] if len(trs) >= 14 else trs
    return round(float(np.mean(window)), 4)


def _summarize_history(symbol: str, bars: list[AssetBar], source: str) -> AssetHistory:
    meta = TICKER_META.get(symbol, {"name": symbol, "role": "Crude Benchmark", "asset_type": "FUT"})
    latest = bars[-1].close
    prev = bars[-2].close if len(bars) >= 2 else latest
    prev5 = bars[-6].close if len(bars) >= 6 else bars[0].close
    chg_1d = ((latest / max(prev, 1e-6)) - 1.0) * 100.0
    ret_5d = ((latest / max(prev5, 1e-6)) - 1.0) * 100.0
    atr = compute_atr_14(bars)
    atr_pct = (atr / max(latest, 1e-6)) * 100.0
    sma_20 = float(np.mean([b.close for b in bars[-20:]])) if bars else latest
    return AssetHistory(
        symbol=symbol,
        name=meta["name"],
        role=meta["role"],
        asset_type=meta["asset_type"],
        source=source,
        bars=bars,
        latest_price=round(latest, 2),
        change_1d_pct=round(chg_1d, 2),
        atr_14=round(atr, 3),
        atr_pct=round(atr_pct, 2),
        sma_20=round(sma_20, 2),
        ret_5d_pct=round(ret_5d, 2),
    )


def _fetch_ticker_sync(symbol: str, period: str = "2y") -> AssetHistory:
    df = yf.Ticker(symbol).history(period=period, interval="1d", auto_adjust=True)
    if df is None or df.empty:
        raise RuntimeError(f"yfinance returned empty history for {symbol}")
    bars: list[AssetBar] = []
    for idx, row in df.iterrows():
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        if any(math.isnan(x) for x in (o, h, l, c)) or c <= 0:
            continue
        vol = float(row.get("Volume", 0.0) or 0.0)
        bars.append(
            AssetBar(
                date=idx.to_pydatetime().date(),
                open=round(o, 2),
                high=round(h, 2),
                low=round(l, 2),
                close=round(c, 2),
                volume=round(vol, 1),
            )
        )
    if len(bars) < 20:
        raise RuntimeError(f"Insufficient valid bars for {symbol}: {len(bars)}")
    return _summarize_history(symbol, bars, source="yfinance")


def simulate_asset_universe(
    days: int = 504,
    shock_series: list[float] | None = None,
    reference_date: date | None = None,
    seed: int = 202611,
) -> dict[str, AssetHistory]:
    """Deterministic multi-year fallback simulator for offline testing if yfinance is blocked."""
    rng = random.Random(seed)
    today = reference_date or datetime.now(timezone.utc).date()

    # Build weekday dates
    dates: list[date] = []
    cur = today
    while len(dates) < days:
        if cur.weekday() < 5:
            dates.append(cur)
        cur -= timedelta(days=1)
    dates.reverse()

    if shock_series is None or len(shock_series) < days:
        shock_series = [
            0.65 * math.sin(i / 28.0) + (0.95 if (days - 180) <= i <= (days - 150) else 0.0)
            + (0.75 if (days - 40) <= i <= (days - 20) else 0.0)
            for i in range(days)
        ]
    else:
        shock_series = shock_series[-days:]

    specs = {
        "BNO": (31.5, 0.016, 1.15),
        "USO": (74.0, 0.015, 0.92),
        "FRO": (21.5, 0.023, 1.35),
        "DHT": (11.2, 0.019, 1.20),
        "STNG": (62.0, 0.021, 1.10),
        "BZ=F": (82.0, 0.016, 1.15),
        "CL=F": (78.0, 0.015, 0.95),
    }

    out: dict[str, AssetHistory] = {}
    for sym, (start_px, vol, beta) in specs.items():
        px = start_px
        bars: list[AssetBar] = []
        for i, d in enumerate(dates):
            lag1 = shock_series[max(0, i - 1)]
            lag2 = shock_series[max(0, i - 2)]
            lag_delta = lag1 - shock_series[max(0, i - 4)]
            ret = 0.0002 + 0.012 * beta * lag_delta + 0.0025 * beta * lag2 + rng.gauss(0.0, vol)
            o = round(px, 2)
            c = round(max(3.0, o * (1.0 + ret)), 2)
            spread = abs(rng.gauss(vol * 0.9, vol * 0.25)) * o
            hi = round(max(o, c) + spread * 0.65, 2)
            lo = round(max(1.0, min(o, c) - spread * 0.65), 2)
            bars.append(AssetBar(date=d, open=o, high=hi, low=lo, close=c, volume=round(1_200_000 * rng.uniform(0.6, 1.8), 1)))
            px = c
        out[sym] = _summarize_history(sym, bars, source="market_simulator")
    return out


async def fetch_tradable_universe(
    symbols: tuple[str, ...] = TRADABLE_TICKERS + ("BZ=F", "CL=F"),
    period: str = "2y",
    feed_mode: Literal["auto", "live", "simulator"] = "auto",
) -> dict[str, AssetHistory]:
    """Fetch 2-year OHLCV histories for BNO, USO, FRO, DHT, STNG (+ BZ=F, CL=F) with automatic fallback."""
    if feed_mode == "simulator":
        return simulate_asset_universe(days=504)

    sim_fallback = simulate_asset_universe(days=504)
    results: dict[str, AssetHistory] = {}

    async def _one(sym: str) -> tuple[str, AssetHistory]:
        try:
            hist = await asyncio.wait_for(asyncio.to_thread(_fetch_ticker_sync, sym, period), timeout=15.0)
            return sym, hist
        except Exception as exc:
            logger.info("yfinance 2y fetch unavailable for %s (%s); using fallback", sym, exc)
            return sym, sim_fallback[sym]

    pairs = await asyncio.gather(*(_one(s) for s in symbols))
    for sym, hist in pairs:
        results[sym] = hist
    return results

"""Deterministic correlated Brent (BZ=F) & WTI (CL=F) candle simulator aligned with Hormuz choke episodes."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

from services.maritime_feed.simulator import HormuzSimulator
from services.market_feed.base import CandleInterval, MarketAdapter, OilCandle, OilSymbol


class MarketSimulator(MarketAdapter):
    """Generates realistic Brent & WTI daily and hourly OHLCV series with 1–3 day lag response to Hormuz shocks."""

    name = "market_simulator"
    tier = "simulator"

    def __init__(self, seed: int = 202604) -> None:
        self.seed = seed

    def is_configured(self) -> bool:
        return True

    def generate_sync(
        self,
        symbol: OilSymbol,
        interval: CandleInterval = "1d",
        days: int = 45,
        reference_date: date | None = None,
    ) -> list[OilCandle]:
        is_brent = symbol == "BZ=F"
        rng = random.Random(self.seed + (101 if is_brent else 202))
        today = reference_date or datetime.now(timezone.utc).date()

        shock_curve = HormuzSimulator.get_shock_profile(days)
        # Lagged shock impulse: oil markets react with a 1-3 day lag to Hormuz tanker slowdowns
        base_price = 78.40 if is_brent else 74.15
        # Brent carries higher seaborne Middle East exposure than landlocked WTI
        shock_sensitivity = 1.15 if is_brent else 0.96

        daily_candles: list[OilCandle] = []
        price = base_price

        for idx in range(days):
            d = today - timedelta(days=(days - 1 - idx))
            lag1 = shock_curve[max(0, idx - 1)]
            lag2 = shock_curve[max(0, idx - 2)]
            lag3 = shock_curve[max(0, idx - 3)]
            lag_shock = 0.45 * lag1 + 0.35 * lag2 + 0.20 * lag3
            prev_lag = shock_curve[max(0, idx - 4)]

            # Mean reversion toward fundamental anchor + lagged choke impulse
            shock_delta = (lag_shock - prev_lag) * 5.8 * shock_sensitivity
            reversion = (base_price + 6.2 * lag_shock * shock_sensitivity - price) * 0.24
            macro_drift = 0.14 * math.sin(idx / 6.5) + rng.gauss(0.0, 0.58)

            open_p = round(price, 2)
            close_p = round(max(55.0, open_p + shock_delta + reversion + macro_drift), 2)
            intraday_vol = (0.75 + 1.15 * lag_shock) * abs(rng.gauss(1.0, 0.25))
            high_p = round(max(open_p, close_p) + intraday_vol * rng.uniform(0.35, 0.85), 2)
            low_p = round(min(open_p, close_p) - intraday_vol * rng.uniform(0.35, 0.85), 2)
            volume = round((260000 if is_brent else 310000) * (1.0 + 0.75 * lag_shock + rng.uniform(-0.12, 0.18)), 1)

            daily_candles.append(
                OilCandle(
                    symbol=symbol,
                    interval="1d",
                    timestamp=datetime(d.year, d.month, d.day, 21, 0, tzinfo=timezone.utc),
                    open=open_p,
                    high=high_p,
                    low=low_p,
                    close=close_p,
                    volume=volume,
                    source=self.name,
                )
            )
            price = close_p

        if interval == "1d":
            return daily_candles

        # Synthesize last 5 days of hourly intraday candles anchored to daily closes
        hourly: list[OilCandle] = []
        recent = daily_candles[-5:]
        for day_c in recent:
            start_dt = day_c.timestamp - timedelta(hours=23)
            cur = day_c.open
            step_drift = (day_c.close - day_c.open) / 24.0
            for h in range(24):
                ts = start_dt + timedelta(hours=h)
                o = round(cur, 2)
                c = round(day_c.close if h == 23 else o + step_drift + rng.gauss(0.0, 0.18), 2)
                hi = round(max(o, c) + rng.uniform(0.05, 0.28), 2)
                lo = round(min(o, c) - rng.uniform(0.05, 0.28), 2)
                hourly.append(
                    OilCandle(
                        symbol=symbol,
                        interval="1h",
                        timestamp=ts,
                        open=o,
                        high=hi,
                        low=lo,
                        close=c,
                        volume=round(day_c.volume / 24.0 * rng.uniform(0.6, 1.5), 1),
                        source=self.name,
                    )
                )
                cur = c
        return hourly

    async def fetch_candles(
        self, symbol: OilSymbol, interval: CandleInterval = "1d", days: int = 45
    ) -> list[OilCandle]:
        return self.generate_sync(symbol=symbol, interval=interval, days=days)

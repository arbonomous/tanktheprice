"""Free live oil market feed using yfinance for Brent Crude (BZ=F) and WTI Crude (CL=F)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import yfinance as yf

from services.market_feed.base import CandleInterval, MarketAdapter, OilCandle, OilSymbol

logger = logging.getLogger(__name__)


class YFinanceAdapter(MarketAdapter):
    """Fetches daily and intraday OHLCV candles for BZ=F and CL=F without an API key."""

    name = "yfinance"
    tier = "free_live"

    def is_configured(self) -> bool:
        return True

    def _fetch_sync(self, symbol: OilSymbol, interval: CandleInterval, days: int) -> list[OilCandle]:
        period = f"{max(days, 60)}d" if interval == "1d" else "7d"
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval, auto_adjust=False)
        if df is None or df.empty:
            raise RuntimeError(f"yfinance returned empty dataframe for {symbol} ({interval})")

        candles: list[OilCandle] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime()
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            if any(x != x for x in (o, h, l, c)):  # NaN guard
                continue
            vol = float(row.get("Volume", 0.0) or 0.0)
            candles.append(
                OilCandle(
                    symbol=symbol,
                    interval=interval,
                    timestamp=ts,
                    open=round(o, 2),
                    high=round(h, 2),
                    low=round(l, 2),
                    close=round(c, 2),
                    volume=round(vol, 1),
                    source=self.name,
                )
            )
        if not candles:
            raise RuntimeError(f"No valid OHLCV rows parsed from yfinance for {symbol}")
        return candles

    async def fetch_candles(
        self, symbol: OilSymbol, interval: CandleInterval = "1d", days: int = 60
    ) -> list[OilCandle]:
        return await asyncio.wait_for(
            asyncio.to_thread(self._fetch_sync, symbol, interval, days),
            timeout=8.0,
        )

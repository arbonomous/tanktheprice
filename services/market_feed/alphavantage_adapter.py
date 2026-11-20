"""Optional Alpha Vantage commodity adapter for Brent & WTI crude oil."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from services.market_feed.base import CandleInterval, MarketAdapter, OilCandle, OilSymbol


class AlphaVantageAdapter(MarketAdapter):
    """Optional paid/keyed Alpha Vantage commodity adapter activated via ALPHAVANTAGE_API_KEY."""

    name = "alphavantage"
    tier = "paid_market"
    ENDPOINT = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str = "", timeout_seconds: float = 8.0) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def fetch_candles(
        self, symbol: OilSymbol, interval: CandleInterval = "1d", days: int = 60
    ) -> list[OilCandle]:
        if not self.is_configured():
            raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")
        if interval != "1d":
            raise RuntimeError("Alpha Vantage commodity endpoint supports daily interval only")

        fn = "BRENT" if symbol == "BZ=F" else "WTI"
        params = {"function": fn, "interval": "daily", "apikey": self.api_key}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(self.ENDPOINT, params=params)
            resp.raise_for_status()
            payload = resp.json()

        rows = payload.get("data") or []
        candles: list[OilCandle] = []
        for row in reversed(rows[:days]):
            val_str = row.get("value", ".")
            if val_str == "." or not val_str:
                continue
            close = round(float(val_str), 2)
            ts = datetime.fromisoformat(row["date"]).replace(tzinfo=timezone.utc)
            candles.append(
                OilCandle(
                    symbol=symbol,
                    interval="1d",
                    timestamp=ts,
                    open=round(close * 0.996, 2),
                    high=round(close * 1.008, 2),
                    low=round(close * 0.991, 2),
                    close=close,
                    volume=240000.0,
                    source=self.name,
                )
            )
        if not candles:
            raise RuntimeError("Alpha Vantage returned no usable oil price data")
        return candles

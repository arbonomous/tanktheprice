"""Base schemas and interface for crude oil market data feeds (Brent BZ=F & WTI CL=F)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

OilSymbol = Literal["BZ=F", "CL=F"]
CandleInterval = Literal["1d", "1h"]


class OilCandle(BaseModel):
    symbol: OilSymbol
    interval: CandleInterval
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str


class MarketAdapter(ABC):
    name: str = "base"
    tier: Literal["free_live", "paid_market", "simulator"] = "free_live"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if credentials/config are ready."""

    @abstractmethod
    async def fetch_candles(
        self, symbol: OilSymbol, interval: CandleInterval = "1d", days: int = 60
    ) -> list[OilCandle]:
        """Fetch OHLCV candles for Brent (BZ=F) or WTI (CL=F)."""

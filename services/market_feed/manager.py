"""Orchestrates oil market data adapters (yfinance primary, Alpha Vantage optional, simulator fallback)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from services.maritime_feed.base import AdapterHealth
from services.market_feed.alphavantage_adapter import AlphaVantageAdapter
from services.market_feed.base import CandleInterval, OilCandle, OilSymbol
from services.market_feed.simulator import MarketSimulator
from services.market_feed.yfinance_adapter import YFinanceAdapter

logger = logging.getLogger(__name__)


class MarketFeedManager:
    """Manages oil market feed fallback and adapter health."""

    def __init__(
        self,
        feed_mode: Literal["auto", "live", "simulator"] = "auto",
        alphavantage_api_key: str = "",
    ) -> None:
        self.feed_mode = feed_mode
        self.yfinance = YFinanceAdapter()
        self.alphavantage = AlphaVantageAdapter(api_key=alphavantage_api_key)
        self.simulator = MarketSimulator()
        self.health_map: dict[str, AdapterHealth] = {}

    def _record_health(
        self,
        name: str,
        tier: Literal["free_live", "paid_market", "simulator"],
        configured: bool,
        active: bool,
        status: Literal["LIVE", "STANDBY_NO_KEY", "FALLBACK_SIMULATOR", "DEGRADED", "DISABLED"],
        message: str,
    ) -> None:
        self.health_map[name] = AdapterHealth(
            name=name,
            category="market",
            tier=tier,
            configured=configured,
            active=active,
            status=status,
            message=message,
            last_checked=datetime.now(timezone.utc),
        )

    async def fetch_all(self, days: int = 45) -> dict[tuple[OilSymbol, CandleInterval], list[OilCandle]]:
        results: dict[tuple[OilSymbol, CandleInterval], list[OilCandle]] = {}
        symbols: list[OilSymbol] = ["BZ=F", "CL=F"]
        intervals: list[CandleInterval] = ["1d", "1h"]

        if self.feed_mode == "simulator":
            self._record_health("yfinance", "free_live", True, False, "DISABLED", "Simulator mode forced")
            self._record_health(
                "alphavantage",
                "paid_market",
                self.alphavantage.is_configured(),
                False,
                "DISABLED" if self.alphavantage.is_configured() else "STANDBY_NO_KEY",
                "Simulator mode forced",
            )
            self._record_health(
                "market_simulator",
                "simulator",
                True,
                True,
                "FALLBACK_SIMULATOR",
                "Serving deterministic Hormuz-correlated Brent & WTI candles",
            )
            for sym in symbols:
                for iv in intervals:
                    results[(sym, iv)] = await self.simulator.fetch_candles(sym, iv, days=days)
            return results

        # Track live status across symbols
        av_ok = False
        yf_ok = False

        if self.alphavantage.is_configured():
            try:
                for sym in symbols:
                    results[(sym, "1d")] = await self.alphavantage.fetch_candles(sym, "1d", days=days)
                av_ok = True
                self._record_health("alphavantage", "paid_market", True, True, "LIVE", "Live daily Brent & WTI via Alpha Vantage")
            except Exception as exc:
                logger.warning("Alpha Vantage adapter failed: %s", exc)
                self._record_health("alphavantage", "paid_market", True, False, "DEGRADED", f"Failed ({type(exc).__name__}); falling back")
        else:
            self._record_health(
                "alphavantage",
                "paid_market",
                False,
                False,
                "STANDBY_NO_KEY",
                "Add ALPHAVANTAGE_API_KEY in .env.local to activate",
            )

        # Primary zero-key yfinance feed
        try:
            for sym in symbols:
                for iv in intervals:
                    if (sym, iv) not in results:
                        results[(sym, iv)] = await self.yfinance.fetch_candles(sym, iv, days=days)
            yf_ok = True
            self._record_health("yfinance", "free_live", True, True, "LIVE", "Live BZ=F (Brent) & CL=F (WTI) via yfinance")
        except Exception as exc:
            logger.info("yfinance unavailable (%s); falling back to MarketSimulator", exc)
            self._record_health(
                "yfinance",
                "free_live",
                True,
                False,
                "DEGRADED",
                "Upstream Yahoo Finance unreachable; using correlated oil simulator",
            )

        used_sim = False
        for sym in symbols:
            for iv in intervals:
                if (sym, iv) not in results:
                    results[(sym, iv)] = await self.simulator.fetch_candles(sym, iv, days=days)
                    used_sim = True

        self._record_health(
            "market_simulator",
            "simulator",
            True,
            used_sim,
            "FALLBACK_SIMULATOR" if used_sim else "DISABLED",
            "Supplying Hormuz-correlated Brent & WTI fallback candles" if used_sim else "Standby (live market feed active)",
        )
        return results

    def get_health(self) -> list[AdapterHealth]:
        return list(self.health_map.values())

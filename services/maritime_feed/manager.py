"""Orchestrates maritime feed adapters with zero-key fallback and seamless live upgrade."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from services.maritime_feed.aisstream import AisStreamAdapter
from services.maritime_feed.base import AdapterHealth, MaritimeFeedPayload
from services.maritime_feed.datalastic import DatalasticAdapter
from services.maritime_feed.hormuz_now import HormuzNowAdapter
from services.maritime_feed.imf_portwatch import ImfPortWatchAdapter
from services.maritime_feed.marinetraffic import MarineTrafficAdapter
from services.maritime_feed.simulator import HormuzSimulator
from services.maritime_feed.straits_live import StraitsLiveAdapter

logger = logging.getLogger(__name__)


class MaritimeFeedManager:
    """Manages maritime adapter fallback order and live health reporting."""

    def __init__(
        self,
        feed_mode: Literal["auto", "live", "simulator"] = "auto",
        straits_live_api_key: str = "",
        datalastic_api_key: str = "",
        marinetraffic_api_key: str = "",
        aisstream_api_key: str = "",
    ) -> None:
        self.feed_mode = feed_mode
        self.straits_live = StraitsLiveAdapter(api_key=straits_live_api_key)
        self.datalastic = DatalasticAdapter(api_key=datalastic_api_key)
        self.marinetraffic = MarineTrafficAdapter(api_key=marinetraffic_api_key)
        self.aisstream = AisStreamAdapter(api_key=aisstream_api_key)
        self.hormuz_now = HormuzNowAdapter()
        self.imf_portwatch = ImfPortWatchAdapter()
        self.simulator = HormuzSimulator()
        self.health_map: dict[str, AdapterHealth] = {}

    def _record_health(
        self,
        name: str,
        tier: Literal["free_live", "paid_ais", "simulator"],
        configured: bool,
        active: bool,
        status: Literal["LIVE", "STANDBY_NO_KEY", "FALLBACK_SIMULATOR", "DEGRADED", "DISABLED"],
        message: str,
    ) -> None:
        self.health_map[name] = AdapterHealth(
            name=name,
            category="maritime",
            tier=tier,
            configured=configured,
            active=active,
            status=status,
            message=message,
            last_checked=datetime.now(timezone.utc),
        )

    async def fetch_all(self, days: int = 45) -> MaritimeFeedPayload:
        # Always generate deterministic baseline first so partial live feeds seamlessly merge
        sim_payload = await self.simulator.fetch(days=days)

        if self.feed_mode == "simulator":
            for adapter in (self.straits_live, self.datalastic, self.marinetraffic):
                self._record_health(
                    adapter.name,
                    "paid_ais",
                    adapter.is_configured(),
                    False,
                    "DISABLED" if adapter.is_configured() else "STANDBY_NO_KEY",
                    "Simulator mode forced via FEED_MODE=simulator",
                )
            for adapter in (self.aisstream, self.hormuz_now, self.imf_portwatch):
                self._record_health(
                    adapter.name,
                    "free_live",
                    adapter.is_configured(),
                    False,
                    "DISABLED" if adapter.is_configured() else "STANDBY_NO_KEY",
                    "Simulator mode forced via FEED_MODE=simulator",
                )
            self._record_health(
                self.simulator.name,
                "simulator",
                True,
                True,
                "FALLBACK_SIMULATOR",
                "Active deterministic 45-day Hormuz traffic & choke simulator",
            )
            return sim_payload

        live_vessels = []
        live_transits = []
        live_gaps = []
        active_sources: list[str] = []

        # 1. Try optional high-resolution paid AIS adapters if keys are configured
        for adapter in (self.straits_live, self.datalastic, self.marinetraffic):
            if not adapter.is_configured():
                self._record_health(
                    adapter.name,
                    "paid_ais",
                    False,
                    False,
                    "STANDBY_NO_KEY",
                    f"Add {adapter.name.upper()}_API_KEY in .env.local to activate",
                )
                continue
            try:
                res = await adapter.fetch(days=days)
                if res.vessels and not live_vessels:
                    live_vessels = res.vessels
                if res.ais_gaps and not live_gaps:
                    live_gaps = res.ais_gaps
                active_sources.append(adapter.name)
                self._record_health(
                    adapter.name,
                    "paid_ais",
                    True,
                    True,
                    "LIVE",
                    f"Ingested {len(res.vessels)} vessels, {len(res.ais_gaps)} AIS gap events",
                )
            except Exception as exc:
                logger.warning("Paid AIS adapter %s failed: %s", adapter.name, exc)
                self._record_health(
                    adapter.name,
                    "paid_ais",
                    True,
                    False,
                    "DEGRADED",
                    f"Request failed ({type(exc).__name__}); falling back",
                )

        # 2. Try free keyed AISStream.io live WebSocket AIS if AISSTREAM_API_KEY is configured
        if self.aisstream.is_configured():
            try:
                res = await self.aisstream.fetch(days=days)
                if res.vessels and not live_vessels:
                    live_vessels = res.vessels
                active_sources.append(self.aisstream.name)
                self._record_health(
                    self.aisstream.name,
                    "free_live",
                    True,
                    True,
                    "LIVE",
                    f"Live WebSocket AIS captured {len(res.vessels)} Strait of Hormuz tankers",
                )
            except Exception as exc:
                logger.info("AISStream.io unavailable (%s); continuing fallback chain", exc)
                self._record_health(
                    self.aisstream.name,
                    "free_live",
                    True,
                    False,
                    "DEGRADED",
                    f"WebSocket error ({type(exc).__name__}); falling back",
                )
        else:
            self._record_health(
                self.aisstream.name,
                "free_live",
                False,
                False,
                "STANDBY_NO_KEY",
                "Add free AISSTREAM_API_KEY (aisstream.io) for live tanker positions",
            )

        # 2. Try primary free live feeds (Hormuz.now & IMF PortWatch)
        for adapter in (self.hormuz_now, self.imf_portwatch):
            try:
                res = await adapter.fetch(days=days)
                if res.vessels and not live_vessels:
                    live_vessels = res.vessels
                if res.daily_transits and len(res.daily_transits) >= 14 and not live_transits:
                    live_transits = res.daily_transits
                if res.ais_gaps and not live_gaps:
                    live_gaps = res.ais_gaps
                active_sources.append(adapter.name)
                self._record_health(
                    adapter.name,
                    "free_live",
                    True,
                    True,
                    "LIVE",
                    f"Live feed connected ({len(res.vessels)} vessels, {len(res.daily_transits)} daily rows)",
                )
            except Exception as exc:
                logger.info("Free live feed %s unavailable (%s); simulator fallback ready", adapter.name, exc)
                self._record_health(
                    adapter.name,
                    "free_live",
                    True,
                    False,
                    "DEGRADED",
                    "Upstream unreachable or blocked; using deterministic Hormuz baseline",
                )

        used_sim_fallback = not (live_vessels and live_transits)
        self._record_health(
            self.simulator.name,
            "simulator",
            True,
            used_sim_fallback,
            "FALLBACK_SIMULATOR" if used_sim_fallback else "DISABLED",
            "Supplying zero-key Hormuz telemetry & 45d history"
            if used_sim_fallback
            else "Standby (all feeds live)",
        )

        source_label = "+".join(active_sources) if active_sources and not used_sim_fallback else (
            f"{'+'.join(active_sources)}+simulator" if active_sources else self.simulator.name
        )

        return MaritimeFeedPayload(
            vessels=live_vessels or sim_payload.vessels,
            daily_transits=live_transits or sim_payload.daily_transits,
            ais_gaps=live_gaps or sim_payload.ais_gaps,
            source=source_label,
        )

    def get_health(self) -> list[AdapterHealth]:
        return list(self.health_map.values())

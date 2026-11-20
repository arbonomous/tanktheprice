"""Optional high-resolution AIS adapter for Straits.live API."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from services.maritime_feed.base import (
    AisGapRecord,
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    is_congestion_loitering,
    is_in_dark_corridor,
    is_outbound_laden,
)

logger = logging.getLogger(__name__)


class StraitsLiveAdapter(MaritimeAdapter):
    """High-resolution AIS adapter integrating /api/v1/transits, /api/v1/ais-gaps, and /api/v1/sanctioned-vessels."""

    name = "straits_live"
    tier = "paid_ais"
    BASE_URL = "https://api.straits.live"

    def __init__(self, api_key: str = "", timeout_seconds: float = 8.0) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        if not self.is_configured():
            raise RuntimeError("STRAITS_LIVE_API_KEY is not configured")

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-API-Key": self.api_key,
            "Accept": "application/json",
        }

        vessels: list[VesselSnapshot] = []
        ais_gaps: list[AisGapRecord] = []
        sanctioned_mmsis: set[str] = set()

        async with httpx.AsyncClient(
            base_url=self.BASE_URL, headers=headers, timeout=self.timeout_seconds
        ) as client:
            # 1. Sanctioned vessels registry
            try:
                s_resp = await client.get("/api/v1/sanctioned-vessels", params={"strait": "hormuz"})
                if s_resp.status_code == 200:
                    s_data = s_resp.json()
                    for item in s_data if isinstance(s_data, list) else s_data.get("vessels", []):
                        if isinstance(item, dict) and item.get("mmsi"):
                            sanctioned_mmsis.add(str(item["mmsi"]))
            except Exception as exc:
                logger.warning("Straits.live /api/v1/sanctioned-vessels error: %s", exc)

            # 2. Live transits
            t_resp = await client.get("/api/v1/transits", params={"strait": "hormuz", "type": "tanker"})
            t_resp.raise_for_status()
            t_data = t_resp.json()
            rows: list[dict[str, Any]] = t_data if isinstance(t_data, list) else t_data.get("transits", [])
            for row in rows:
                lat = float(row.get("lat", 26.2))
                lon = float(row.get("lon", 56.4))
                speed = float(row.get("speed", 11.0))
                heading = float(row.get("heading", 120.0)) % 360.0
                draft = float(row.get("draft", 15.0))
                dwt = int(row.get("dwt", 280000))
                mmsi = str(row.get("mmsi", "000000000"))
                is_sanctioned = bool(row.get("sanctioned")) or (mmsi in sanctioned_mmsis)

                vclass = "VLCC" if dwt >= 240000 else ("Suezmax" if dwt >= 125000 else "Aframax")
                bbl = 2.0 if vclass == "VLCC" else (1.0 if vclass == "Suezmax" else 0.7)

                if row.get("ais_gap_active"):
                    status = "ais_gap"
                elif is_congestion_loitering(lat, lon, speed):
                    status = "loitering"
                elif is_outbound_laden(heading, draft):
                    status = "outbound_laden"
                else:
                    status = "inbound_ballast"

                vessels.append(
                    VesselSnapshot(
                        mmsi=mmsi,
                        imo=str(row.get("imo", f"IMO{mmsi[:7]}")),
                        name=str(row.get("name", "TANKER")).upper(),
                        vessel_class=vclass,
                        flag=str(row.get("flag", "MH")).upper()[:3],
                        lat=lat,
                        lon=lon,
                        speed_knots=speed,
                        heading=heading,
                        draft_m=draft,
                        destination=str(row.get("destination", "SINGAPORE")).upper(),
                        status=status,
                        is_sanctioned=is_sanctioned,
                        dwt=dwt,
                        barrel_capacity=bbl,
                        ais_gap_hours=float(row.get("ais_gap_hours", 0.0)),
                        last_seen=datetime.now(timezone.utc),
                        source=self.name,
                    )
                )

            # 3. AIS gap events
            try:
                g_resp = await client.get("/api/v1/ais-gaps", params={"strait": "hormuz", "days": min(days, 30)})
                if g_resp.status_code == 200:
                    g_data = g_resp.json()
                    for g in g_data if isinstance(g_data, list) else g_data.get("events", []):
                        lat = float(g.get("last_lat", 26.3))
                        lon = float(g.get("last_lon", 56.4))
                        dur = float(g.get("duration_hours", 6.0))
                        mmsi = str(g.get("mmsi", "000000000"))
                        in_corr = is_in_dark_corridor(lat, lon)
                        ais_gaps.append(
                            AisGapRecord(
                                vessel_mmsi=mmsi,
                                vessel_name=str(g.get("vessel_name", "UNKNOWN")).upper(),
                                vessel_class=g.get("vessel_class", "VLCC"),
                                start_time=datetime.fromisoformat(g["start_time"])
                                if g.get("start_time")
                                else datetime.now(timezone.utc),
                                duration_hours=dur,
                                last_lat=lat,
                                last_lon=lon,
                                in_corridor=in_corr,
                                is_sanctioned=bool(g.get("sanctioned")) or (mmsi in sanctioned_mmsis),
                                severity="CRITICAL" if (in_corr and dur >= 12) else ("HIGH" if in_corr else "MEDIUM"),
                                source=self.name,
                            )
                        )
            except Exception as exc:
                logger.warning("Straits.live /api/v1/ais-gaps error: %s", exc)

        return MaritimeFeedPayload(
            vessels=vessels,
            daily_transits=[],
            ais_gaps=ais_gaps,
            source=self.name,
        )

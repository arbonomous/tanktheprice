"""Free live maritime adapter for Hormuz.now public chokepoint endpoints."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from services.maritime_feed.base import (
    DailyTransitPoint,
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselSnapshot,
)
from services.signal_engine.geometry import is_congestion_loitering, is_in_strait, is_outbound_laden

logger = logging.getLogger(__name__)


class HormuzNowAdapter(MaritimeAdapter):
    """Pulls public JSON/CSV chokepoint transit data from hormuz.now."""

    name = "hormuz_now"
    tier = "free_live"

    BASE_URL = "https://hormuz.now"
    TRAFFIC_ENDPOINT = "/api/traffic"
    CROSSINGS_ENDPOINT = "/api/crossings"
    DATA_ENDPOINT = "/data"

    def __init__(self, timeout_seconds: float = 5.0) -> None:
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        # Public zero-key endpoint
        return True

    def _classify_vessel(self, raw: dict[str, Any]) -> VesselSnapshot | None:
        try:
            lat = float(raw.get("lat") or raw.get("latitude") or 0.0)
            lon = float(raw.get("lon") or raw.get("longitude") or 0.0)
            if not is_in_strait(lat, lon):
                return None
            speed = float(raw.get("speed") or raw.get("sog") or 0.0)
            heading = float(raw.get("heading") or raw.get("cog") or 0.0) % 360.0
            draft = float(raw.get("draft") or raw.get("draught") or 11.5)
            dwt = int(raw.get("dwt") or 160000)

            if dwt >= 240000:
                vclass, bbl = "VLCC", 2.0
            elif dwt >= 125000:
                vclass, bbl = "Suezmax", 1.0
            else:
                vclass, bbl = "Aframax", 0.7

            if raw.get("ais_gap") or raw.get("dark"):
                status = "ais_gap"
            elif is_congestion_loitering(lat, lon, speed):
                status = "loitering"
            elif is_outbound_laden(heading, draft):
                status = "outbound_laden"
            else:
                status = "inbound_ballast"

            return VesselSnapshot(
                mmsi=str(raw.get("mmsi") or raw.get("id") or "000000000"),
                imo=str(raw.get("imo") or f"IMO{str(raw.get('mmsi', '9000000'))[:7]}"),
                name=str(raw.get("name") or raw.get("shipname") or "UNKNOWN TANKER").upper(),
                vessel_class=vclass,
                flag=str(raw.get("flag") or "PA").upper()[:3],
                lat=round(lat, 5),
                lon=round(lon, 5),
                speed_knots=round(speed, 1),
                heading=round(heading, 1),
                draft_m=round(draft, 1),
                destination=str(raw.get("destination") or "GULF OF OMAN").upper(),
                status=status,
                is_sanctioned=bool(raw.get("sanctioned", False)),
                dwt=dwt,
                barrel_capacity=bbl,
                ais_gap_hours=float(raw.get("ais_gap_hours") or 0.0),
                last_seen=datetime.now(timezone.utc),
                source=self.name,
            )
        except Exception:
            return None

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        vessels: list[VesselSnapshot] = []
        daily_transits: list[DailyTransitPoint] = []

        async with httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "HormuzFlow/1.0 (+maritime-intelligence)"},
        ) as client:
            # 1. Fetch live traffic snapshot
            try:
                resp = await client.get(self.TRAFFIC_ENDPOINT)
                if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                    payload = resp.json()
                    rows = payload if isinstance(payload, list) else payload.get("vessels", payload.get("data", []))
                    for row in rows:
                        if isinstance(row, dict):
                            v = self._classify_vessel(row)
                            if v:
                                vessels.append(v)
            except Exception as exc:
                logger.debug("Hormuz.now /api/traffic unavailable: %s", exc)

            # 2. Fetch daily crossings history
            for endpoint in (self.CROSSINGS_ENDPOINT, self.DATA_ENDPOINT):
                if daily_transits:
                    break
                try:
                    resp = await client.get(endpoint)
                    if resp.status_code == 200 and "application/json" in resp.headers.get("content-type", ""):
                        payload = resp.json()
                        rows = payload if isinstance(payload, list) else payload.get("crossings", payload.get("data", []))
                        for row in rows[-days:]:
                            if not isinstance(row, dict) or "date" not in row:
                                continue
                            d = date.fromisoformat(str(row["date"])[:10])
                            outbound = int(row.get("outbound_laden", row.get("outbound", 0)))
                            inbound = int(row.get("inbound_ballast", row.get("inbound", 0)))
                            vlcc = int(row.get("vlcc", max(1, round(outbound * 0.42))))
                            suez = int(row.get("suezmax", max(1, round(outbound * 0.33))))
                            afra = int(row.get("aframax", max(0, outbound - vlcc - suez)))
                            tonnage = round(vlcc * 0.30 + suez * 0.15 + afra * 0.105, 3)
                            barrels = round(vlcc * 2.0 + suez * 1.0 + afra * 0.7, 2)
                            daily_transits.append(
                                DailyTransitPoint(
                                    transit_date=d,
                                    outbound_laden_count=outbound,
                                    inbound_ballast_count=inbound,
                                    vlcc_count=vlcc,
                                    suezmax_count=suez,
                                    aframax_count=afra,
                                    outbound_tonnage_mt=tonnage,
                                    outbound_barrels_mbbl=barrels,
                                    avg_speed_knots=float(row.get("avg_speed", 11.8)),
                                    loitering_count=int(row.get("loitering", 3)),
                                    ais_gap_count=int(row.get("ais_gaps", 2)),
                                    source=self.name,
                                )
                            )
                except Exception as exc:
                    logger.debug("Hormuz.now %s unavailable: %s", endpoint, exc)

        if not vessels and not daily_transits:
            raise RuntimeError("Hormuz.now endpoints returned no usable data")

        return MaritimeFeedPayload(
            vessels=vessels,
            daily_transits=daily_transits,
            ais_gaps=[],
            source=self.name,
        )

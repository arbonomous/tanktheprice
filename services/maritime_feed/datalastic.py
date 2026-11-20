"""Optional high-resolution AIS adapter for Datalastic vessels_in_radius endpoint."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from services.maritime_feed.base import (
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    CHOKEPOINT_CENTER,
    is_congestion_loitering,
    is_outbound_laden,
)


class DatalasticAdapter(MaritimeAdapter):
    """Queries Datalastic vessel_inradius around Strait of Hormuz (lat=26.566, lon=56.25, radius=45 NM)."""

    name = "datalastic"
    tier = "paid_ais"
    ENDPOINT = "https://api.datalastic.com/api/v0/vessel_inradius"

    def __init__(self, api_key: str = "", timeout_seconds: float = 8.0) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        if not self.is_configured():
            raise RuntimeError("DATALASTIC_API_KEY is not configured")

        lat0, lon0 = CHOKEPOINT_CENTER
        params = {
            "api-key": self.api_key,
            "lat": lat0,
            "lon": lon0,
            "radius": 45,
            "type": "Tanker",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(self.ENDPOINT, params=params)
            resp.raise_for_status()
            payload = resp.json()

        vessels: list[VesselSnapshot] = []
        rows = (payload.get("data") or {}).get("vessels") or []
        for row in rows:
            lat = float(row.get("lat") or 0.0)
            lon = float(row.get("lon") or 0.0)
            speed = float(row.get("speed") or 0.0)
            heading = float(row.get("course") or row.get("heading") or 0.0) % 360.0
            draft = float(row.get("draught") or 12.0)
            dwt = int(row.get("deadweight") or 160000)

            vclass = "VLCC" if dwt >= 240000 else ("Suezmax" if dwt >= 125000 else "Aframax")
            bbl = 2.0 if vclass == "VLCC" else (1.0 if vclass == "Suezmax" else 0.7)

            if is_congestion_loitering(lat, lon, speed):
                status = "loitering"
            elif is_outbound_laden(heading, draft):
                status = "outbound_laden"
            else:
                status = "inbound_ballast"

            vessels.append(
                VesselSnapshot(
                    mmsi=str(row.get("mmsi", "000000000")),
                    imo=str(row.get("imo") or f"IMO{str(row.get('mmsi', '9000000'))[:7]}"),
                    name=str(row.get("name", "TANKER")).upper(),
                    vessel_class=vclass,
                    flag=str(row.get("country_iso", "PA")).upper()[:3],
                    lat=round(lat, 5),
                    lon=round(lon, 5),
                    speed_knots=round(speed, 1),
                    heading=round(heading, 1),
                    draft_m=round(draft, 1),
                    destination=str(row.get("destination") or "FUJAIRAH").upper(),
                    status=status,
                    is_sanctioned=False,
                    dwt=dwt,
                    barrel_capacity=bbl,
                    ais_gap_hours=0.0,
                    last_seen=datetime.now(timezone.utc),
                    source=self.name,
                )
            )

        return MaritimeFeedPayload(
            vessels=vessels,
            daily_transits=[],
            ais_gaps=[],
            source=self.name,
        )

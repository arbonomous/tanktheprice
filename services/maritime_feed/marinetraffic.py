"""Optional high-resolution AIS adapter slot for MarineTraffic PS07 / ExportVessels API."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx

from services.maritime_feed.base import (
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    STRAIT_BBOX,
    is_congestion_loitering,
    is_outbound_laden,
)


class MarineTrafficAdapter(MaritimeAdapter):
    """Queries MarineTraffic ExportVessels bounding-box endpoint when MARINETRAFFIC_API_KEY is supplied."""

    name = "marinetraffic"
    tier = "paid_ais"
    BASE_URL = "https://services.marinetraffic.com/api/exportvessels/v:8"

    def __init__(self, api_key: str = "", timeout_seconds: float = 8.0) -> None:
        self.api_key = (api_key or "").strip()
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        if not self.is_configured():
            raise RuntimeError("MARINETRAFFIC_API_KEY is not configured")

        url = (
            f"{self.BASE_URL}/{self.api_key}"
            f"/MINLAT:{STRAIT_BBOX['lat_min']}/MAXLAT:{STRAIT_BBOX['lat_max']}"
            f"/MINLON:{STRAIT_BBOX['lon_min']}/MAXLON:{STRAIT_BBOX['lon_max']}"
            "/shiptype:8/protocol:jsono"
        )
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            rows = resp.json()

        vessels: list[VesselSnapshot] = []
        for row in rows if isinstance(rows, list) else []:
            lat = float(row.get("LAT", 26.2))
            lon = float(row.get("LON", 56.4))
            speed = float(row.get("SPEED", 110)) / 10.0  # MarineTraffic returns 1/10 knot
            heading = float(row.get("HEADING", row.get("COURSE", 120))) % 360.0
            draft = float(row.get("DRAUGHT", 130)) / 10.0
            dwt = int(row.get("DWT", 160000))

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
                    mmsi=str(row.get("MMSI", "000000000")),
                    imo=str(row.get("IMO", "IMO9000000")),
                    name=str(row.get("SHIPNAME", "TANKER")).upper(),
                    vessel_class=vclass,
                    flag=str(row.get("FLAG", "PA")).upper()[:3],
                    lat=round(lat, 5),
                    lon=round(lon, 5),
                    speed_knots=round(speed, 1),
                    heading=round(heading, 1),
                    draft_m=round(draft, 1),
                    destination=str(row.get("DESTINATION", "ASIA")).upper(),
                    status=status,
                    is_sanctioned=False,
                    dwt=dwt,
                    barrel_capacity=bbl,
                    ais_gap_hours=0.0,
                    last_seen=datetime.now(timezone.utc),
                    source=self.name,
                )
            )

        return MaritimeFeedPayload(vessels=vessels, daily_transits=[], ais_gaps=[], source=self.name)

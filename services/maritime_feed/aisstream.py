"""Free real-time WebSocket AIS adapter for AISStream.io (Strait of Hormuz bounding box)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import websockets

from services.maritime_feed.base import (
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselClass,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    STRAIT_BBOX,
    is_congestion_loitering,
    is_in_strait,
    is_outbound_laden,
)

logger = logging.getLogger(__name__)


class AisStreamAdapter(MaritimeAdapter):
    """
    Connects to wss://stream.aisstream.io/v0/stream using a free AISSTREAM_API_KEY,
    listens for live tanker PositionReport + ShipStaticData inside Strait of Hormuz
    for a snapshot window, and returns normalized VesselSnapshot records.
    """

    name = "aisstream"
    tier = "free_live"
    WS_URL = "wss://stream.aisstream.io/v0/stream"

    def __init__(self, api_key: str = "", listen_seconds: float | None = None) -> None:
        self.api_key = (api_key or "").strip()
        env_sec = os.getenv("AISSTREAM_LISTEN_SECONDS")
        self.listen_seconds = float(listen_seconds if listen_seconds is not None else (env_sec or 25.0))

    def is_configured(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _estimate_class_and_dwt(length_m: float, draft_m: float) -> tuple[VesselClass, int, float]:
        if length_m >= 300 or draft_m >= 18.0:
            return "VLCC", 305000, 2.02
        if length_m >= 250 or draft_m >= 14.5:
            return "Suezmax", 155000, 1.02
        return "Aframax", 110000, 0.72

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        if not self.is_configured():
            raise RuntimeError("AISSTREAM_API_KEY is not configured")

        # Subscribe to Strait of Hormuz + immediate Fujairah/Persian Gulf approaches
        subscribe_msg = {
            "APIKey": self.api_key,
            "BoundingBoxes": [
                [
                    [STRAIT_BBOX["lat_min"] - 0.5, STRAIT_BBOX["lon_min"] - 0.5],
                    [STRAIT_BBOX["lat_max"] + 0.5, STRAIT_BBOX["lon_max"] + 0.5],
                ]
            ],
            "FilterMessageTypes": [
                "PositionReport",
                "StandardClassBPositionReport",
                "ShipStaticData",
            ],
        }

        positions: dict[str, dict[str, Any]] = {}
        statics: dict[str, dict[str, Any]] = {}
        raw_count = 0

        deadline = asyncio.get_running_loop().time() + self.listen_seconds
        async with websockets.connect(self.WS_URL, open_timeout=10.0, close_timeout=3.0) as ws:
            await ws.send(json.dumps(subscribe_msg))
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    break
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=min(3.0, remaining))
                except asyncio.TimeoutError:
                    continue
                except Exception as exc:
                    logger.info("AISStream socket closed early: %s", exc)
                    break

                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")

                try:
                    msg = json.loads(raw)
                except Exception:
                    continue

                if "error" in msg or "Error" in msg:
                    err_txt = msg.get("error") or msg.get("Error")
                    raise RuntimeError(f"AISStream API error: {err_txt}")

                raw_count += 1
                meta = msg.get("MetaData") or {}
                mmsi = str(meta.get("MMSI") or meta.get("MMSI_String") or "").strip()
                if not mmsi:
                    continue

                msg_type = msg.get("MessageType")
                body = (msg.get("Message") or {}).get(msg_type or "", {})

                if msg_type in ("PositionReport", "StandardClassBPositionReport"):
                    lat = float(meta.get("latitude") or body.get("Latitude") or 0.0)
                    lon = float(meta.get("longitude") or body.get("Longitude") or 0.0)
                    if not (23.5 <= lat <= 28.5 and 54.5 <= lon <= 59.0):
                        continue
                    sog = float(body.get("Sog") or 0.0)
                    hdg = float(body.get("TrueHeading") or body.get("Cog") or 0.0)
                    if hdg >= 360.0 or hdg < 0.0:
                        hdg = float(body.get("Cog") or 0.0) % 360.0
                    positions[mmsi] = {
                        "name": str(meta.get("ShipName") or f"VESSEL {mmsi}").strip().upper(),
                        "lat": lat,
                        "lon": lon,
                        "speed": sog,
                        "heading": hdg % 360.0,
                    }
                elif msg_type == "ShipStaticData":
                    ship_type = int(body.get("Type") or 0)
                    dim = body.get("Dimension") or {}
                    length = float(dim.get("A", 0) or 0) + float(dim.get("B", 0) or 0)
                    statics[mmsi] = {
                        "ship_type": ship_type,
                        "imo": str(body.get("ImoNumber") or ""),
                        "draft": float(body.get("MaximumStaticDraught") or 0.0),
                        "destination": str(body.get("Destination") or "").strip().upper(),
                        "name": str(body.get("Name") or meta.get("ShipName") or "").strip().upper(),
                        "length": length,
                    }

        logger.info(
            "AISStream window complete (%.0fs): %d raw msgs, %d unique positions, %d static records",
            self.listen_seconds,
            raw_count,
            len(positions),
            len(statics),
        )

        # Prefer tankers (ShipType 80..89) or unclassified large vessels; if none identified yet, keep live Strait vessels
        tanker_candidates: list[VesselSnapshot] = []
        all_candidates: list[VesselSnapshot] = []
        now_utc = datetime.now(timezone.utc)

        for mmsi, pos in positions.items():
            st = statics.get(mmsi, {})
            ship_type = st.get("ship_type", 0)
            lat, lon, spd, hdg = pos["lat"], pos["lon"], pos["speed"], pos["heading"]
            # Clamp slightly outside Strait bbox into view only if inside monitoring box
            if not is_in_strait(lat, lon):
                continue

            draft = float(st.get("draft") or (14.6 if (90.0 <= hdg <= 160.0 and spd >= 4.0) else 9.8))
            length = float(st.get("length") or 260.0)
            vclass, dwt, bbl = self._estimate_class_and_dwt(length, draft)

            if is_congestion_loitering(lat, lon, spd):
                status = "loitering"
            elif is_outbound_laden(hdg, draft):
                status = "outbound_laden"
            else:
                status = "inbound_ballast"

            imo_num = st.get("imo") or mmsi[:7]
            imo = imo_num if imo_num.startswith("IMO") else f"IMO{imo_num}"

            snap = VesselSnapshot(
                mmsi=mmsi,
                imo=imo,
                name=(st.get("name") or pos["name"] or f"VESSEL {mmsi}").strip(),
                vessel_class=vclass,
                flag=mmsi[:3],
                lat=round(lat, 5),
                lon=round(lon, 5),
                speed_knots=round(spd, 1),
                heading=round(hdg, 1),
                draft_m=round(draft, 1),
                destination=st.get("destination") or "STRAIT OF HORMUZ",
                status=status,
                is_sanctioned=False,
                dwt=dwt,
                barrel_capacity=bbl,
                ais_gap_hours=0.0,
                last_seen=now_utc,
                source=self.name,
            )
            all_candidates.append(snap)
            if ship_type == 0 or (80 <= ship_type <= 89):
                tanker_candidates.append(snap)

        vessels = tanker_candidates if len(tanker_candidates) >= 5 else all_candidates
        if not vessels:
            raise RuntimeError(
                f"AISStream returned zero Strait of Hormuz vessels ({raw_count} raw msgs in {self.listen_seconds:.0f}s)"
            )

        return MaritimeFeedPayload(vessels=vessels, daily_transits=[], ais_gaps=[], source=self.name)

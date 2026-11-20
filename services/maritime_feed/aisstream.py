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
    is_outbound_laden,
)

logger = logging.getLogger(__name__)


class AisStreamAdapter(MaritimeAdapter):
    """
    Connects to wss://stream.aisstream.io/v0/stream using a free AISSTREAM_API_KEY,
    listens for live PositionReport / Class B / LongRangeAisBroadcastMessage / ShipStaticData
    across the Strait of Hormuz & approaches, and returns normalized VesselSnapshot records.
    """

    name = "aisstream"
    tier = "free_live"
    WS_URL = "wss://stream.aisstream.io/v0/stream"

    def __init__(self, api_key: str = "", listen_seconds: float | None = None) -> None:
        self.api_key = (api_key or "").strip()
        env_sec = os.getenv("AISSTREAM_LISTEN_SECONDS")
        self.listen_seconds = float(listen_seconds if listen_seconds is not None else (env_sec or 30.0))

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

        # Subscribe without FilterMessageTypes so we receive PositionReport, Class B,
        # LongRangeAisBroadcastMessage (type 27), and ShipStaticData across Strait + approaches
        subscribe_msg = {
            "APIKey": self.api_key,
            "BoundingBoxes": [
                [
                    [23.0, 53.5],
                    [28.5, 59.5],
                ]
            ],
        }

        positions: dict[str, dict[str, Any]] = {}
        statics: dict[str, dict[str, Any]] = {}
        msg_type_counts: dict[str, int] = {}
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
                msg_type = str(msg.get("MessageType") or "Unknown")
                msg_type_counts[msg_type] = msg_type_counts.get(msg_type, 0) + 1
                if raw_count <= 2:
                    logger.info(
                        "AISStream sample msg #%d keys=%s type=%s",
                        raw_count,
                        list(msg.keys()),
                        msg_type,
                    )

                meta = msg.get("MetaData") or {}
                mmsi = str(meta.get("MMSI") or meta.get("MMSI_String") or "").strip()
                if not mmsi:
                    continue

                body = (msg.get("Message") or {}).get(msg_type, {}) or {}
                lat = float(meta.get("latitude") or body.get("Latitude") or 0.0)
                lon = float(meta.get("longitude") or body.get("Longitude") or 0.0)

                if msg_type == "ShipStaticData":
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

                # Any AIS message carrying valid MetaData coordinates inside Hormuz/Gulf approaches
                if 23.0 <= lat <= 28.5 and 53.5 <= lon <= 59.5:
                    sog = float(body.get("Sog") or positions.get(mmsi, {}).get("speed") or 0.0)
                    hdg = float(body.get("TrueHeading") or body.get("Cog") or positions.get(mmsi, {}).get("heading") or 0.0)
                    if hdg >= 360.0 or hdg < 0.0:
                        hdg = float(body.get("Cog") or 0.0) % 360.0
                    positions[mmsi] = {
                        "name": str(meta.get("ShipName") or positions.get(mmsi, {}).get("name") or f"VESSEL {mmsi}").strip().upper(),
                        "lat": lat,
                        "lon": lon,
                        "speed": sog,
                        "heading": hdg % 360.0,
                    }

        logger.info(
            "AISStream window complete (%.0fs): %d raw msgs, %d unique vessels, types=%s",
            self.listen_seconds,
            raw_count,
            len(positions),
            msg_type_counts,
        )

        tanker_candidates: list[VesselSnapshot] = []
        all_candidates: list[VesselSnapshot] = []
        now_utc = datetime.now(timezone.utc)

        for mmsi, pos in positions.items():
            st = statics.get(mmsi, {})
            ship_type = st.get("ship_type", 0)
            lat, lon, spd, hdg = pos["lat"], pos["lon"], pos["speed"], pos["heading"]

            # Keep vessels in Strait of Hormuz + immediate approaches (23.5–28.2N, 54.5–59.0E)
            if not (
                STRAIT_BBOX["lat_min"] - 0.5 <= lat <= STRAIT_BBOX["lat_max"] + 0.2
                and STRAIT_BBOX["lon_min"] - 0.5 <= lon <= STRAIT_BBOX["lon_max"] + 0.5
            ):
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

        vessels = tanker_candidates if len(tanker_candidates) >= 3 else all_candidates
        if not vessels:
            raise RuntimeError(
                f"AISStream returned zero Strait of Hormuz vessels ({raw_count} raw msgs, types={msg_type_counts})"
            )

        return MaritimeFeedPayload(vessels=vessels, daily_transits=[], ais_gaps=[], source=self.name)

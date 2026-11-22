"""Free live maritime adapter for Hormuz.now public CC-BY-4.0 chokepoint & live AIS endpoints."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any

import httpx

from services.maritime_feed.base import (
    AisGapRecord,
    DailyTransitPoint,
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselClass,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    is_congestion_loitering,
    is_in_dark_corridor,
    is_in_strait,
    is_outbound_laden,
)

logger = logging.getLogger(__name__)


def _pick(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for k in keys:
        if k in d and d[k] is not None and d[k] != "":
            return d[k]
    return default


class HormuzNowAdapter(MaritimeAdapter):
    """
    Pulls real-time Strait of Hormuz vessel positions (/api/snapshot), daily crossings
    (/api/daily.json, /api/traffic), 2-year IMF PortWatch history (/api/portwatch),
    waiting queues & AIS-silent ships (/api/areas), and Gulf port exports (/api/ports)
    from hormuz.now (CC BY 4.0).
    """

    name = "hormuz_now"
    tier = "free_live"

    BASE_URL = "https://hormuz.now"
    SNAPSHOT_ENDPOINT = "/api/snapshot"
    DAILY_ENDPOINT = "/api/daily.json"
    TRAFFIC_ENDPOINT = "/api/traffic"
    PORTWATCH_ENDPOINT = "/api/portwatch"
    AREAS_ENDPOINT = "/api/areas"
    PORTS_ENDPOINT = "/api/ports"
    STATUS_ENDPOINT = "/status.json"

    def __init__(self, timeout_seconds: float = 12.0) -> None:
        self.timeout_seconds = timeout_seconds

    def is_configured(self) -> bool:
        return True

    @staticmethod
    def _is_tanker_row(raw: dict[str, Any]) -> bool:
        cat = str(
            _pick(raw, "category", "cat", "shipCategory", "vesselType", "typeLabel", "typeName", "type", default="")
        ).lower()
        if any(k in cat for k in ("tanker", "crude", "oil", "lng", "lpg", "chemical", "product", "vlcc", "suezmax", "aframax")):
            return True
        code = _pick(raw, "aisType", "shipType", "typeCode", "shiptype")
        try:
            if code is not None and 80 <= int(code) <= 89:
                return True
        except Exception:
            pass
        return False

    def _parse_vessel(self, raw: dict[str, Any], now_utc: datetime) -> VesselSnapshot | None:
        try:
            lat = float(_pick(raw, "lat", "latitude", "la", default=0.0))
            lon = float(_pick(raw, "lon", "lng", "longitude", "lo", default=0.0))
            if not is_in_strait(lat, lon):
                return None

            speed = float(_pick(raw, "speed", "sog", "sp", "spd", default=0.0))
            raw_hdg = float(_pick(raw, "heading", "hdg", "cog", "course", "co", default=0.0))
            heading = (raw_hdg % 360.0) if 0.0 <= raw_hdg < 360.0 else (float(_pick(raw, "cog", "course", default=0.0)) % 360.0)

            length = float(_pick(raw, "length", "len", "loa", default=0.0))
            draft_val = _pick(raw, "draft", "draught", "dr")
            draft = float(draft_val) if draft_val is not None else (
                15.2 if (90.0 <= heading <= 160.0 and speed >= 4.0) else 10.2
            )
            if draft > 35.0:
                draft = draft / 10.0

            dwt_val = _pick(raw, "dwt", "deadweight")
            if dwt_val is not None:
                dwt = int(float(dwt_val))
            elif length >= 300 or draft >= 18.0:
                dwt = 305000
            elif length >= 245 or draft >= 14.5:
                dwt = 155000
            else:
                dwt = 110000

            vclass: VesselClass
            if dwt >= 240000 or length >= 300:
                vclass, bbl = "VLCC", 2.02
            elif dwt >= 125000 or length >= 245:
                vclass, bbl = "Suezmax", 1.02
            else:
                vclass, bbl = "Aframax", 0.72

            gap_hours = float(_pick(raw, "aisGapHours", "silentHours", "gapHours", default=0.0))
            is_dark = bool(_pick(raw, "aisGap", "dark", "silent", "isSilent", default=False)) or gap_hours >= 3.0

            if is_dark:
                status = "ais_gap"
            elif is_congestion_loitering(lat, lon, speed):
                status = "loitering"
            elif is_outbound_laden(heading, draft):
                status = "outbound_laden"
            else:
                status = "inbound_ballast"

            mmsi = str(_pick(raw, "mmsi", "id", "vesselId", default="000000000"))
            raw_imo = str(_pick(raw, "imo", default="")).strip()
            imo = raw_imo if raw_imo.upper().startswith("IMO") else (f"IMO{raw_imo}" if raw_imo else f"IMO{mmsi[:7]}")
            name = str(_pick(raw, "name", "shipName", "shipname", "vesselName", default=f"TANKER {mmsi}")).strip().upper()
            flag = str(_pick(raw, "flag", "flagCode", "country", "countryCode", default=mmsi[:2])).strip().upper()[:3]
            dest = str(_pick(raw, "destination", "dest", "declaredDestination", default="STRAIT OF HORMUZ")).strip().upper() or "STRAIT OF HORMUZ"

            ts_raw = _pick(raw, "t", "ts", "timestamp", "lastSeen", "updatedAt")
            if isinstance(ts_raw, (int, float)) and ts_raw > 1_000_000_000:
                last_seen = datetime.fromtimestamp(ts_raw / 1000.0 if ts_raw > 1e11 else ts_raw, tz=timezone.utc)
            else:
                last_seen = now_utc

            return VesselSnapshot(
                mmsi=mmsi,
                imo=imo,
                name=name,
                vessel_class=vclass,
                flag=flag,
                lat=round(lat, 5),
                lon=round(lon, 5),
                speed_knots=round(speed, 1),
                heading=round(heading, 1),
                draft_m=round(draft, 1),
                destination=dest,
                status=status,
                is_sanctioned=bool(_pick(raw, "sanctioned", "isSanctioned", default=False)),
                dwt=dwt,
                barrel_capacity=bbl,
                ais_gap_hours=round(gap_hours, 1),
                last_seen=last_seen,
                source=self.name,
            )
        except Exception:
            return None

    @staticmethod
    def _parse_daily_row(row: dict[str, Any], source: str) -> DailyTransitPoint | None:
        raw_d = _pick(row, "date", "day", "d")
        if not raw_d:
            return None
        try:
            d = date.fromisoformat(str(raw_d)[:10])
        except Exception:
            return None

        # PortWatch rows use n_tanker / tankers / tanker / n_total; daily.json uses in / out / tankers / total
        tankers_raw = _pick(row, "n_tanker", "tankers", "tanker", "tanker_transits")
        out_raw = _pick(row, "out", "outbound", "outbound_laden")
        in_raw = _pick(row, "in", "inbound", "inbound_ballast")
        total_raw = _pick(row, "total", "n_total", "transits")

        if out_raw is not None:
            outbound = max(0, int(round(float(out_raw))))
            inbound = max(0, int(round(float(in_raw or 0))))
        elif tankers_raw is not None:
            t_cnt = max(0, int(round(float(tankers_raw))))
            outbound = round(t_cnt * 0.52)
            inbound = max(0, t_cnt - outbound)
        elif total_raw is not None:
            tot = max(0, int(round(float(total_raw))))
            outbound = round(tot * 0.29)
            inbound = round(tot * 0.27)
        else:
            return None

        vlcc = max(0, round(outbound * 0.44))
        suez = max(0, round(outbound * 0.34))
        afra = max(0, outbound - vlcc - suez)
        cap_raw = float(_pick(row, "capacity_tanker", "tankerCapacity", "dwt", default=0.0) or 0.0)
        cap_mt = cap_raw / 1_000_000.0 if cap_raw > 10_000 else cap_raw
        tonnage = round(cap_mt * 0.52, 3) if cap_mt > 0.05 else round(vlcc * 0.305 + suez * 0.155 + afra * 0.108, 3)
        barrels = round(vlcc * 2.02 + suez * 1.02 + afra * 0.72, 2)

        return DailyTransitPoint(
            transit_date=d,
            outbound_laden_count=outbound,
            inbound_ballast_count=inbound,
            vlcc_count=vlcc,
            suezmax_count=suez,
            aframax_count=afra,
            outbound_tonnage_mt=tonnage,
            outbound_barrels_mbbl=barrels,
            avg_speed_knots=round(float(_pick(row, "avgSpeed", "avg_speed", default=11.4)), 2),
            loitering_count=max(0, int(_pick(row, "waiting", "loitering", default=max(2, round(max(0, 22 - outbound) * 0.6))))),
            ais_gap_count=max(0, int(_pick(row, "aisGaps", "silent", default=2))),
            congestion_index=round(min(95.0, max(10.0, 72.0 - outbound * 2.3)), 1),
            source=source,
        )

    async def fetch_rich_context(self, days: int = 730) -> dict[str, Any]:
        """
        Fetch 2-year stitched daily history (/api/portwatch + /api/daily.json),
        plus live waiting queues (/status.json, /api/areas) and Gulf port exports (/api/ports).
        """
        context: dict[str, Any] = {
            "history_transits": [],
            "waiting_gulf": 0,
            "waiting_oman": 0,
            "fleet_total": 0,
            "fleet_tankers": 0,
            "gulf_export_pct_normal": 100.0,
            "ais_silent_count": 0,
            "status_level": "unknown",
            "status_pct_normal": None,
            "source": self.name,
        }

        by_date: dict[date, DailyTransitPoint] = {}

        try:
            client_ctx = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self.timeout_seconds,
                follow_redirects=True,
                headers={"User-Agent": "HormuzFlow/2.0 (+https://github.com/arbonomous/tanktheprice)"},
            )
        except Exception as exc:
            logger.info("hormuz.now rich context client unavailable (%s); using fallback", exc)
            return context

        async with client_ctx as client:
            # 1. Multi-year IMF PortWatch history stored on hormuz.now (/api/portwatch)
            try:
                resp = await client.get(self.PORTWATCH_ENDPOINT)
                if resp.status_code == 200:
                    pdata = resp.json()
                    rows = (
                        pdata
                        if isinstance(pdata, list)
                        else (pdata.get("days") or pdata.get("daily") or pdata.get("series") or pdata.get("data") or [])
                    )
                    if rows and isinstance(rows[0], dict):
                        logger.info("hormuz.now /api/portwatch rows=%d keys=%s", len(rows), list(rows[0].keys())[:10])
                    for row in rows[-days:]:
                        if isinstance(row, dict):
                            pt = self._parse_daily_row(row, source="imf_portwatch")
                            if pt:
                                by_date[pt.transit_date] = pt
            except Exception as exc:
                logger.info("hormuz.now /api/portwatch unavailable: %s", exc)

            # 2. Stitch latest live daily crossings on top (/api/daily.json)
            try:
                resp = await client.get(self.DAILY_ENDPOINT)
                if resp.status_code == 200:
                    ddata = resp.json()
                    rows = (
                        ddata
                        if isinstance(ddata, list)
                        else (ddata.get("days") or ddata.get("daily") or ddata.get("data") or [])
                    )
                    for row in rows:
                        if isinstance(row, dict):
                            pt = self._parse_daily_row(row, source=self.name)
                            if pt:
                                by_date[pt.transit_date] = pt
            except Exception as exc:
                logger.info("hormuz.now /api/daily.json unavailable: %s", exc)

            # 3. Live status + waiting queues (/status.json)
            try:
                resp = await client.get(self.STATUS_ENDPOINT)
                if resp.status_code == 200:
                    sdata = resp.json()
                    if isinstance(sdata, dict):
                        fleet = sdata.get("fleet") or {}
                        st = sdata.get("status") or {}
                        context["waiting_gulf"] = int(fleet.get("waitingGulf") or 0)
                        context["waiting_oman"] = int(fleet.get("waitingOman") or 0)
                        context["fleet_total"] = int(fleet.get("vessels") or 0)
                        context["fleet_tankers"] = int(fleet.get("tankers") or 0)
                        context["status_level"] = str(st.get("level") or "unknown")
                        if st.get("pct") is not None:
                            context["status_pct_normal"] = round(float(st["pct"]), 1)
            except Exception as exc:
                logger.debug("hormuz.now /status.json unavailable: %s", exc)

            # 4. AIS-silent count from /api/areas
            try:
                resp = await client.get(self.AREAS_ENDPOINT)
                if resp.status_code == 200:
                    adata = resp.json()
                    if isinstance(adata, dict):
                        silent_obj = (
                            adata.get("aisSilent")
                            or adata.get("silentShips")
                            or adata.get("silent")
                            or adata.get("aisSilentShips")
                        )
                        if isinstance(silent_obj, list):
                            context["ais_silent_count"] = len(silent_obj)
                        elif isinstance(silent_obj, dict):
                            lst = silent_obj.get("ships") or silent_obj.get("vessels") or silent_obj.get("list") or []
                            context["ais_silent_count"] = int(silent_obj.get("count") or len(lst))
                        elif isinstance(silent_obj, (int, float)):
                            context["ais_silent_count"] = int(silent_obj)
            except Exception as exc:
                logger.debug("hormuz.now /api/areas context unavailable: %s", exc)

            # 5. Gulf export calls vs. pre-crisis normal from /api/ports
            try:
                resp = await client.get(self.PORTS_ENDPOINT)
                if resp.status_code == 200:
                    pdata = resp.json()
                    ports = pdata if isinstance(pdata, list) else (pdata.get("ports") or pdata.get("data") or [])
                    shares = []
                    for p in ports:
                        if not isinstance(p, dict):
                            continue
                        sh = _pick(p, "shareOfNormal", "pctNormal", "pct", "ratio")
                        if sh is not None:
                            val = float(sh)
                            shares.append(val * 100.0 if val <= 2.5 else val)
                    if shares:
                        context["gulf_export_pct_normal"] = round(sum(shares) / len(shares), 1)
            except Exception as exc:
                logger.debug("hormuz.now /api/ports unavailable: %s", exc)

        ordered = sorted(by_date.values(), key=lambda x: x.transit_date)[-days:]
        context["history_transits"] = ordered
        logger.info(
            "hormuz.now rich context: %d history days | waitingGulf=%d waitingOman=%d | gulfExports=%.1f%% | aisSilent=%d",
            len(ordered),
            context["waiting_gulf"],
            context["waiting_oman"],
            context["gulf_export_pct_normal"],
            context["ais_silent_count"],
        )
        return context

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        vessels: list[VesselSnapshot] = []
        daily_transits: list[DailyTransitPoint] = []
        ais_gaps: list[AisGapRecord] = []
        now_utc = datetime.now(timezone.utc)

        async with httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=self.timeout_seconds,
            follow_redirects=True,
            headers={"User-Agent": "HormuzFlow/2.0 (+https://github.com/arbonomous/tanktheprice)"},
        ) as client:
            # 1. Live vessels from /api/snapshot
            try:
                resp = await client.get(self.SNAPSHOT_ENDPOINT)
                if resp.status_code == 200:
                    payload = resp.json()
                    rows = (
                        payload
                        if isinstance(payload, list)
                        else (payload.get("vessels") or payload.get("ships") or payload.get("data") or [])
                    )
                    tanker_rows = [r for r in rows if isinstance(r, dict) and self._is_tanker_row(r)]
                    chosen_rows = tanker_rows if len(tanker_rows) >= 10 else [r for r in rows if isinstance(r, dict)]

                    parsed: list[VesselSnapshot] = []
                    for row in chosen_rows:
                        v = self._parse_vessel(row, now_utc)
                        if v:
                            parsed.append(v)

                    parsed.sort(
                        key=lambda v: (
                            1 if v.status == "ais_gap" else 0,
                            1 if v.status == "outbound_laden" else 0,
                            1 if is_in_dark_corridor(v.lat, v.lon) else 0,
                            v.speed_knots >= 3.0,
                            v.dwt,
                        ),
                        reverse=True,
                    )
                    vessels = parsed[:120]
                    logger.info(
                        "hormuz.now /api/snapshot parsed %d tankers/vessels in Strait (from %d total rows, %d tankers)",
                        len(vessels),
                        len(rows),
                        len(tanker_rows),
                    )
            except Exception as exc:
                logger.info("hormuz.now /api/snapshot error: %s", exc)

            # 2. Daily crossings from /api/daily.json (fallback /api/traffic)
            for endpoint in (self.DAILY_ENDPOINT, self.TRAFFIC_ENDPOINT):
                if daily_transits:
                    break
                try:
                    resp = await client.get(endpoint)
                    if resp.status_code != 200:
                        continue
                    payload = resp.json()
                    rows = (
                        payload
                        if isinstance(payload, list)
                        else (payload.get("days") or payload.get("daily") or payload.get("crossings") or payload.get("data") or [])
                    )
                    for row in rows[-days:]:
                        if isinstance(row, dict):
                            pt = self._parse_daily_row(row, source=self.name)
                            if pt:
                                daily_transits.append(pt)
                except Exception as exc:
                    logger.info("hormuz.now %s error: %s", endpoint, exc)

            # 3. AIS-silent ships from /api/areas
            try:
                resp = await client.get(self.AREAS_ENDPOINT)
                if resp.status_code == 200:
                    adata = resp.json()
                    if isinstance(adata, dict):
                        silent_list = (
                            adata.get("aisSilent")
                            or adata.get("silentShips")
                            or adata.get("silent")
                            or adata.get("aisSilentShips")
                            or []
                        )
                        if isinstance(silent_list, dict):
                            silent_list = silent_list.get("ships") or silent_list.get("vessels") or silent_list.get("list") or []
                        for item in (silent_list if isinstance(silent_list, list) else [])[:25]:
                            if not isinstance(item, dict):
                                continue
                            lat = float(_pick(item, "lat", "lastLat", "latitude", default=26.25))
                            lon = float(_pick(item, "lon", "lng", "lastLon", "longitude", default=56.40))
                            dur = float(_pick(item, "silentHours", "gapHours", "hours", default=8.0))
                            mmsi = str(_pick(item, "mmsi", "id", default="000000000"))
                            in_corr = is_in_dark_corridor(lat, lon)
                            ais_gaps.append(
                                AisGapRecord(
                                    vessel_mmsi=mmsi,
                                    vessel_name=str(_pick(item, "name", "shipName", default=f"VESSEL {mmsi}")).upper(),
                                    vessel_class="VLCC",
                                    start_time=now_utc,
                                    end_time=None,
                                    duration_hours=round(dur, 1),
                                    last_lat=round(lat, 5),
                                    last_lon=round(lon, 5),
                                    in_corridor=in_corr,
                                    is_sanctioned=bool(_pick(item, "sanctioned", default=False)),
                                    severity="CRITICAL" if dur >= 14.0 else ("HIGH" if in_corr else "MEDIUM"),
                                    source=self.name,
                                )
                            )
            except Exception as exc:
                logger.debug("hormuz.now /api/areas error: %s", exc)

        if not vessels and not daily_transits:
            raise RuntimeError("Hormuz.now endpoints returned no usable data")

        return MaritimeFeedPayload(
            vessels=vessels,
            daily_transits=daily_transits,
            ais_gaps=ais_gaps,
            source=self.name,
        )

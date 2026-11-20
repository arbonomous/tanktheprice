"""Deterministic Strait of Hormuz maritime traffic, AIS-dark, and geopolitical choke simulator."""

from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone

from services.maritime_feed.base import (
    AisGapRecord,
    DailyTransitPoint,
    MaritimeAdapter,
    MaritimeFeedPayload,
    VesselClass,
    VesselSnapshot,
)
from services.signal_engine.geometry import (
    INBOUND_LANE_SPINE,
    OUTBOUND_LANE_SPINE,
    is_in_dark_corridor,
)

# Realistic tanker names grouped by class/operator style
VLCC_NAMES = [
    "FRONT ALTAIR", "EURONAV OCEANUS", "DHT JAGUAR", "MARAN CENTAURUS", "NEW VISION",
    "SEAWAYS KILIMANJARO", "NORDIC HARRIER", "COSGLORY LAKE", "OLYMPIC LUCK", "AL SALHEIA",
    "SAUDI GLORY", "BAHRI YANBU", "PACIFIC VOYAGER", "STARLIGHT VENTURE", "KASHIMA MARU",
    "TI EUROPE", "SINOPEAK CRUDE", "GULF CROWN", "HORMUZ SOVEREIGN", "NAVE BUENA SUERTE",
    "ARABIAN TITAN", "EASTERN HORIZON", "EMIRATES EAGLE", "QATAR SPIRIT", "PERSIAN STAR",
]

SUEZMAX_NAMES = [
    "NORDIC BREEZE", "DELTA POSEIDON", "MINERVA SOPHIA", "SCF SAKHALIN", "STENA SUPREME",
    "GENMAR ATLAS", "OLYMPIC FLAME", "AEGEAN FREEDOM", "CAPE BASTIA", "SEAVIGOUR",
    "CRUDE TRADER", "AL KHOR", "UMM AL QUWAIN", "BENGAL SPIRIT", "MAERSK SARATOGA",
    "NAVION OCEANIA", "DESH VISHAL", "SUEZ PROSPECT", "MARAN HELEN", "SONANGOL CABINDA",
]

AFRAMAX_NAMES = [
    "NS ANTARCTIC", "STI RUBY", "HAFNIA LION", "SCORPIO VANGUARD", "EAGLE TORONTO",
    "SEA EXPRESS", "CORAL LEADER", "GULF PEARL", "FUJAIRAH VENTURE", "MUSANDAM TRADER",
    "KHOR FAKKAN STAR", "OMAN CREST", "ARABIAN DAWN", "SHARJAH WAVE", "BANDAR EXPRESS",
    "AL DHAFRA", "SOHAR MARINER", "CRESCENT BAY", "DUNE RUNNER", "JEBEL ALI SPIRIT",
    "DARK PHOENIX", "CASPIAN SHADOW", "MIRAGE CARRIER",
]

OUTBOUND_DESTS = [
    "NINGBO", "SINGAPORE", "ULSAN", "SIKKA", "CHIBA", "ZHOUSHAN",
    "VADINAR", "YEOSU", "ROTTERDAM", "AIN SUKHNA", "KIIRE", "RIZHAO",
]

INBOUND_DESTS = [
    "RAS TANURA", "AL BASRAH", "KHARG ISLAND", "MINA AL AHMADI",
    "JUBAIL", "DAS ISLAND", "MESAIEED", "RUWAIS", "FUJAIRAH",
]

FLAGS = ["MH", "LR", "PA", "SG", "GR", "SA", "AE", "HK", "BS", "CY", "IR", "CM"]


def _interpolate_spine(
    spine: list[tuple[float, float]], t: float
) -> tuple[float, float, float]:
    """Interpolate (lat, lon, bearing_deg) along a polyline spine for t in [0, 1]."""
    t = max(0.0, min(0.9999, t))
    n_seg = len(spine) - 1
    scaled = t * n_seg
    idx = min(int(scaled), n_seg - 1)
    frac = scaled - idx
    lat1, lon1 = spine[idx]
    lat2, lon2 = spine[idx + 1]
    lat = lat1 + (lat2 - lat1) * frac
    lon = lon1 + (lon2 - lon1) * frac

    # Compass bearing (0=N, 90=E, 180=S, 270=W)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(math.radians(lat2))
    x = math.cos(math.radians(lat1)) * math.sin(math.radians(lat2)) - (
        math.sin(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.cos(dlon)
    )
    bearing = (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
    return lat, lon, bearing


class HormuzSimulator(MaritimeAdapter):
    """Deterministic zero-key simulator seeding 45 days of Hormuz transits, dark-fleet gaps, and live vessels."""

    name = "hormuz_simulator"
    tier = "simulator"

    def __init__(self, seed: int = 202604) -> None:
        self.seed = seed

    def is_configured(self) -> bool:
        return True

    @staticmethod
    def get_shock_profile(days: int) -> list[float]:
        """Deterministic geopolitical choke intensity curve [0..1] aligned with market simulator."""
        profile = [0.0] * days
        # Episode 1: ~34 days ago (brief maritime inspection slowdown)
        c1 = max(2, days - 34)
        # Episode 2: ~18 days ago (major TSS congestion + dark-fleet surge)
        c2 = max(5, days - 18)
        # Episode 3: Current emerging tightening over last 4 days
        c3 = days - 2

        for i in range(days):
            e1 = 0.58 * math.exp(-((i - c1) ** 2) / 4.5)
            e2 = 0.88 * math.exp(-((i - c2) ** 2) / 5.5)
            e3 = 0.52 * math.exp(-((i - c3) ** 2) / 4.0)
            profile[i] = min(1.0, e1 + e2 + e3)
        return profile

    def generate_sync(self, days: int = 45, reference_date: date | None = None) -> MaritimeFeedPayload:
        rng = random.Random(self.seed)
        today = reference_date or datetime.now(timezone.utc).date()
        now_utc = datetime.now(timezone.utc).replace(second=0, microsecond=0)

        shock_curve = self.get_shock_profile(days)
        daily_transits: list[DailyTransitPoint] = []

        # 1. Generate 45 days of historical chokepoint transits
        for idx in range(days):
            d = today - timedelta(days=(days - 1 - idx))
            shock = shock_curve[idx]
            seasonal = 1.8 * math.sin(2.0 * math.pi * idx / 7.0)

            # Baseline ~23 outbound laden tankers/day (~17-19 Mbbl/d equivalent in large crude/product tankers)
            base_outbound = 23.0 + seasonal + rng.gauss(0.0, 1.3)
            outbound = max(9, round(base_outbound * (1.0 - 0.42 * shock)))
            inbound = max(10, round((21.5 - 0.4 * seasonal + rng.gauss(0.0, 1.4)) * (1.0 - 0.22 * shock)))

            # Class split: VLCC takes bigger hit during geopolitical tension
            vlcc_share = max(0.28, 0.44 - 0.10 * shock + rng.uniform(-0.03, 0.03))
            suez_share = 0.34 + rng.uniform(-0.02, 0.02)
            vlcc = max(2, round(outbound * vlcc_share))
            suez = max(2, round(outbound * suez_share))
            afra = max(1, outbound - vlcc - suez)

            tonnage = round(vlcc * 0.305 + suez * 0.155 + afra * 0.108, 3)
            barrels = round(vlcc * 2.02 + suez * 1.02 + afra * 0.72, 2)
            avg_speed = round(max(7.2, 12.1 - 3.6 * shock + rng.gauss(0.0, 0.28)), 2)
            loitering = max(1, round(3.0 + 13.0 * shock + rng.uniform(-1.0, 1.8)))
            ais_gaps = max(0, round(1.5 + 8.5 * shock + rng.uniform(-0.7, 1.4)))
            congestion = round(min(100.0, max(5.0, 16.0 + 72.0 * shock + rng.gauss(0.0, 4.0))), 1)

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
                    avg_speed_knots=avg_speed,
                    loitering_count=loitering,
                    ais_gap_count=ais_gaps,
                    congestion_index=congestion,
                    source=self.name,
                )
            )

        # 2. Generate ~68 realistic live vessels inside Strait of Hormuz (24.0-28.0N, 55.0-58.5E)
        vessels: list[VesselSnapshot] = []
        ais_gaps: list[AisGapRecord] = []

        name_pool: list[tuple[str, VesselClass, int, float]] = (
            [(n, "VLCC", rng.randint(295000, 319000), 2.02) for n in VLCC_NAMES]
            + [(n, "Suezmax", rng.randint(148000, 162000), 1.02) for n in SUEZMAX_NAMES]
            + [(n, "Aframax", rng.randint(102000, 118000), 0.72) for n in AFRAMAX_NAMES]
        )
        rng.shuffle(name_pool)

        # Distribution: 24 outbound_laden, 21 inbound_ballast, 14 loitering, 9 ais_gap = 68 tankers
        status_buckets = (
            ["outbound_laden"] * 24
            + ["inbound_ballast"] * 21
            + ["loitering"] * 14
            + ["ais_gap"] * 9
        )

        for i, status in enumerate(status_buckets):
            name, vclass, dwt, bbl = name_pool[i % len(name_pool)]
            mmsi = f"{rng.choice(['241', '352', '477', '538', '563', '636', '422', '403'])}{100000 + i * 1371 + rng.randint(10, 99)}"[:9]
            imo = f"IMO{9300000 + i * 2411 + rng.randint(10, 99)}"
            flag = rng.choice(FLAGS[:10])
            is_sanctioned = False
            gap_hours = 0.0

            if status == "outbound_laden":
                t = (i + rng.uniform(0.15, 0.85)) / 24.0
                lat, lon, bearing = _interpolate_spine(OUTBOUND_LANE_SPINE, t)
                lat += rng.uniform(-0.04, 0.04)
                lon += rng.uniform(-0.04, 0.04)
                # Ensure outbound heading sits cleanly inside 090°-160°
                heading = max(92.0, min(158.0, bearing + rng.uniform(-6.0, 6.0)))
                speed = round(rng.uniform(10.2, 14.4), 1)
                draft = round(rng.uniform(16.8, 21.4) if vclass == "VLCC" else rng.uniform(13.2, 16.5), 1)
                dest = rng.choice(OUTBOUND_DESTS)

            elif status == "inbound_ballast":
                t = ((i - 24) + rng.uniform(0.15, 0.85)) / 21.0
                lat, lon, bearing = _interpolate_spine(INBOUND_LANE_SPINE, t)
                lat += rng.uniform(-0.04, 0.04)
                lon += rng.uniform(-0.04, 0.04)
                heading = (bearing + rng.uniform(-7.0, 7.0)) % 360.0
                speed = round(rng.uniform(10.8, 14.8), 1)
                draft = round(rng.uniform(7.8, 11.2), 1)
                dest = rng.choice(INBOUND_DESTS)

            elif status == "loitering":
                zone = i % 3
                if zone == 0:
                    # Idling outside Fujairah designated anchorage box
                    lat = round(rng.uniform(25.18, 25.68), 5)
                    lon = round(rng.uniform(56.62, 57.10), 5)
                    dest = "FUJAIRAH ORDERS"
                elif zone == 1:
                    # Idling near Bandar Abbas approach outside anchorage
                    lat = round(rng.uniform(26.78, 26.98), 5)
                    lon = round(rng.uniform(56.25, 56.62), 5)
                    dest = "BANDAR ABBAS WAIT"
                else:
                    # Slowed inside TSS bottleneck near Musandam
                    lat = round(rng.uniform(26.18, 26.44), 5)
                    lon = round(rng.uniform(56.26, 56.62), 5)
                    dest = "HORMUZ TRANSIT DELAY"
                heading = round(rng.uniform(80.0, 310.0), 1)
                speed = round(rng.uniform(0.4, 2.6), 1)
                draft = round(rng.uniform(13.5, 20.1) if i % 2 == 0 else rng.uniform(8.8, 11.5), 1)

            else:
                # AIS Gap / Dark-fleet vessel inside 25.5°N–27.0°N, 55.8°E–57.0°E corridor
                lat = round(rng.uniform(25.65, 26.86), 5)
                lon = round(rng.uniform(55.92, 56.92), 5)
                heading = round(rng.uniform(95.0, 155.0), 1)
                speed = round(rng.uniform(6.4, 11.8), 1)
                draft = round(rng.uniform(14.0, 20.6), 1)
                dest = rng.choice(["FOR ORDERS", "SINGAPORE EOPL", "UNKNOWN", "ZHOUSHAN"])
                flag = rng.choice(["IR", "CM", "PA", "GA", "PW"])
                is_sanctioned = (i % 2 == 0)
                gap_hours = round(rng.uniform(4.5, 22.0), 1)

                start_ts = now_utc - timedelta(hours=gap_hours)
                in_corr = is_in_dark_corridor(lat, lon)
                ais_gaps.append(
                    AisGapRecord(
                        vessel_mmsi=mmsi,
                        vessel_name=name,
                        vessel_class=vclass,
                        start_time=start_ts,
                        end_time=None,
                        duration_hours=gap_hours,
                        last_lat=lat,
                        last_lon=lon,
                        reappeared_lat=None,
                        reappeared_lon=None,
                        in_corridor=in_corr,
                        is_sanctioned=is_sanctioned,
                        severity="CRITICAL" if (is_sanctioned or gap_hours >= 14.0) else "HIGH",
                        source=self.name,
                    )
                )

            vessels.append(
                VesselSnapshot(
                    mmsi=mmsi,
                    imo=imo,
                    name=name,
                    vessel_class=vclass,
                    flag=flag,
                    lat=round(lat, 5),
                    lon=round(lon, 5),
                    speed_knots=speed,
                    heading=round(heading, 1),
                    draft_m=draft,
                    destination=dest,
                    status=status,
                    is_sanctioned=is_sanctioned,
                    dwt=dwt,
                    barrel_capacity=bbl,
                    ais_gap_hours=gap_hours,
                    last_seen=now_utc - timedelta(hours=gap_hours) if gap_hours > 0 else now_utc - timedelta(minutes=rng.randint(1, 14)),
                    source=self.name,
                )
            )

        # Add 12 historical resolved AIS-gap events from the past 21 days for dark-fleet log depth
        for k in range(12):
            v_name, v_class, _, _ = name_pool[(k + 5) % len(name_pool)]
            days_ago = rng.randint(1, 21)
            dur = round(rng.uniform(3.5, 18.5), 1)
            start_ts = now_utc - timedelta(days=days_ago, hours=rng.randint(1, 16))
            end_ts = start_ts + timedelta(hours=dur)
            lat = round(rng.uniform(25.58, 26.92), 5)
            lon = round(rng.uniform(55.88, 56.95), 5)
            ais_gaps.append(
                AisGapRecord(
                    vessel_mmsi=f"422{600000 + k * 719}",
                    vessel_name=v_name,
                    vessel_class=v_class,
                    start_time=start_ts,
                    end_time=end_ts,
                    duration_hours=dur,
                    last_lat=lat,
                    last_lon=lon,
                    reappeared_lat=round(lat - rng.uniform(0.15, 0.45), 5),
                    reappeared_lon=round(lon + rng.uniform(0.25, 0.65), 5),
                    in_corridor=is_in_dark_corridor(lat, lon),
                    is_sanctioned=(k % 3 == 0),
                    severity="HIGH" if dur >= 10.0 else "MEDIUM",
                    source=self.name,
                )
            )

        ais_gaps.sort(key=lambda x: x.start_time, reverse=True)

        return MaritimeFeedPayload(
            vessels=vessels,
            daily_transits=daily_transits,
            ais_gaps=ais_gaps,
            source=self.name,
        )

    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        return self.generate_sync(days=days)

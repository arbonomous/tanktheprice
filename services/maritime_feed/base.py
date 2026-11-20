"""Base models and abstract adapter interface for maritime tanker feeds."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

VesselClass = Literal["VLCC", "Suezmax", "Aframax", "LR2", "MR"]
VesselStatus = Literal["outbound_laden", "inbound_ballast", "loitering", "ais_gap"]


class VesselSnapshot(BaseModel):
    mmsi: str
    imo: str
    name: str
    vessel_class: VesselClass
    flag: str
    lat: float
    lon: float
    speed_knots: float
    heading: float
    draft_m: float
    destination: str
    status: VesselStatus
    is_sanctioned: bool = False
    dwt: int
    barrel_capacity: float  # million barrels (Mbbl)
    ais_gap_hours: float = 0.0
    last_seen: datetime
    source: str


class DailyTransitPoint(BaseModel):
    transit_date: date
    outbound_laden_count: int
    inbound_ballast_count: int
    vlcc_count: int
    suezmax_count: int
    aframax_count: int
    outbound_tonnage_mt: float  # million metric tons DWT
    outbound_barrels_mbbl: float  # million barrels
    avg_speed_knots: float
    loitering_count: int
    ais_gap_count: int
    congestion_index: float = 0.0
    source: str


class AisGapRecord(BaseModel):
    vessel_mmsi: str
    vessel_name: str
    vessel_class: VesselClass
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_hours: float
    last_lat: float
    last_lon: float
    reappeared_lat: Optional[float] = None
    reappeared_lon: Optional[float] = None
    in_corridor: bool
    is_sanctioned: bool = False
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "MEDIUM"
    source: str


class AdapterHealth(BaseModel):
    name: str
    category: Literal["maritime", "market"]
    tier: Literal["free_live", "paid_ais", "paid_market", "simulator"]
    configured: bool
    active: bool
    status: Literal["LIVE", "STANDBY_NO_KEY", "FALLBACK_SIMULATOR", "DEGRADED", "DISABLED"]
    message: str
    last_checked: datetime = Field(default_factory=datetime.utcnow)


class MaritimeFeedPayload(BaseModel):
    vessels: list[VesselSnapshot] = Field(default_factory=list)
    daily_transits: list[DailyTransitPoint] = Field(default_factory=list)
    ais_gaps: list[AisGapRecord] = Field(default_factory=list)
    source: str


class MaritimeAdapter(ABC):
    name: str = "base"
    tier: Literal["free_live", "paid_ais", "simulator"] = "free_live"

    @abstractmethod
    def is_configured(self) -> bool:
        """Return True if this adapter has required credentials/config."""

    @abstractmethod
    async def fetch(self, days: int = 45) -> MaritimeFeedPayload:
        """Fetch live vessels, historical daily transits, and AIS gap events."""

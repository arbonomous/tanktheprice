"""SQLAlchemy ORM models for HormuzFlow maritime intelligence and crude oil candles."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class VesselRecord(Base):
    __tablename__ = "vessels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mmsi: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    imo: Mapped[str] = mapped_column(String(20), index=True)
    name: Mapped[str] = mapped_column(String(120))
    vessel_class: Mapped[str] = mapped_column(String(20), index=True)
    flag: Mapped[str] = mapped_column(String(10))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    speed_knots: Mapped[float] = mapped_column(Float)
    heading: Mapped[float] = mapped_column(Float)
    draft_m: Mapped[float] = mapped_column(Float)
    destination: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(30), index=True)
    is_sanctioned: Mapped[bool] = mapped_column(Boolean, default=False)
    dwt: Mapped[int] = mapped_column(Integer)
    barrel_capacity: Mapped[float] = mapped_column(Float)
    ais_gap_hours: Mapped[float] = mapped_column(Float, default=0.0)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(50))


class DailyTransitRecord(Base):
    __tablename__ = "daily_transits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transit_date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    outbound_laden_count: Mapped[int] = mapped_column(Integer)
    inbound_ballast_count: Mapped[int] = mapped_column(Integer)
    vlcc_count: Mapped[int] = mapped_column(Integer)
    suezmax_count: Mapped[int] = mapped_column(Integer)
    aframax_count: Mapped[int] = mapped_column(Integer)
    outbound_tonnage_mt: Mapped[float] = mapped_column(Float)
    outbound_barrels_mbbl: Mapped[float] = mapped_column(Float)
    avg_speed_knots: Mapped[float] = mapped_column(Float)
    loitering_count: Mapped[int] = mapped_column(Integer)
    ais_gap_count: Mapped[int] = mapped_column(Integer)
    congestion_index: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50))


class AisGapEventRecord(Base):
    __tablename__ = "ais_gap_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vessel_mmsi: Mapped[str] = mapped_column(String(20), index=True)
    vessel_name: Mapped[str] = mapped_column(String(120))
    vessel_class: Mapped[str] = mapped_column(String(20))
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_hours: Mapped[float] = mapped_column(Float)
    last_lat: Mapped[float] = mapped_column(Float)
    last_lon: Mapped[float] = mapped_column(Float)
    reappeared_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    reappeared_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_corridor: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sanctioned: Mapped[bool] = mapped_column(Boolean, default=False)
    severity: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(50))


class OilCandleRecord(Base):
    __tablename__ = "oil_candles"
    __table_args__ = (UniqueConstraint("symbol", "interval", "timestamp", name="uq_oil_candle"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    interval: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    open: Mapped[float] = mapped_column(Float)
    high: Mapped[float] = mapped_column(Float)
    low: Mapped[float] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(50))


class SignalSnapshotRecord(Base):
    __tablename__ = "signal_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    supply_shock_score: Mapped[float] = mapped_column(Float)
    flow_delta_7d_vs_30d_pct: Mapped[float] = mapped_column(Float)
    congestion_index: Mapped[float] = mapped_column(Float)
    dark_fleet_spike_score: Mapped[float] = mapped_column(Float)
    brent_bias: Mapped[str] = mapped_column(String(16))
    wti_bias: Mapped[str] = mapped_column(String(16))
    predicted_24h_brent_pct: Mapped[float] = mapped_column(Float)
    predicted_72h_brent_pct: Mapped[float] = mapped_column(Float)
    confidence_low_pct: Mapped[float] = mapped_column(Float)
    confidence_high_pct: Mapped[float] = mapped_column(Float)
    backtest_accuracy_pct: Mapped[float] = mapped_column(Float)

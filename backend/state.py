"""Ingestion pipeline, SQLite persistence, and cached quantitative signal state."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import delete, select

from backend.config import settings
from backend.database import SessionLocal, init_db
from backend.models import (
    AisGapEventRecord,
    DailyTransitRecord,
    OilCandleRecord,
    SignalSnapshotRecord,
    VesselRecord,
)
from services.maritime_feed import (
    AdapterHealth,
    AisGapRecord,
    DailyTransitPoint,
    MaritimeFeedManager,
    VesselSnapshot,
)
from services.market_feed import CandleInterval, MarketFeedManager, OilCandle, OilSymbol
from services.signal_engine import SignalAnalysisOutput, run_signal_engine

logger = logging.getLogger(__name__)


class HormuzDataService:
    """Singleton service managing feed ingestion, SQLite persistence, and signal evaluation."""

    def __init__(self) -> None:
        self.feed_mode: Literal["auto", "live", "simulator"] = settings.feed_mode
        self.maritime_manager = MaritimeFeedManager(
            feed_mode=self.feed_mode,
            straits_live_api_key=settings.straits_live_api_key,
            datalastic_api_key=settings.datalastic_api_key,
            marinetraffic_api_key=settings.marinetraffic_api_key,
            aisstream_api_key=settings.aisstream_api_key,
        )
        self.market_manager = MarketFeedManager(
            feed_mode=self.feed_mode,
            alphavantage_api_key=settings.alphavantage_api_key,
        )
        self._lock = asyncio.Lock()
        self.last_refreshed: datetime = datetime.now(timezone.utc)
        self.maritime_source: str = "hormuz_simulator"
        self.market_source: str = "market_simulator"
        self.cached_signal: SignalAnalysisOutput | None = None

    def set_feed_mode(self, mode: Literal["auto", "live", "simulator"]) -> None:
        self.feed_mode = mode
        self.maritime_manager.feed_mode = mode
        self.market_manager.feed_mode = mode

    async def ingest_and_recompute(self, days: int = 45) -> SignalAnalysisOutput:
        async with self._lock:
            init_db()
            maritime_payload, market_map = await asyncio.gather(
                self.maritime_manager.fetch_all(days=days),
                self.market_manager.fetch_all(days=days),
            )
            self.maritime_source = maritime_payload.source
            brent_daily = market_map[("BZ=F", "1d")]
            wti_daily = market_map[("CL=F", "1d")]
            self.market_source = brent_daily[-1].source if brent_daily else "market_simulator"

            signal_out = run_signal_engine(
                vessels=maritime_payload.vessels,
                ais_gaps=maritime_payload.ais_gaps,
                daily_transits=maritime_payload.daily_transits,
                brent_candles=brent_daily,
                wti_candles=wti_daily,
            )

            # Persist snapshots cleanly inside SQLite transaction
            with SessionLocal() as db:
                db.execute(delete(VesselRecord))
                for v in maritime_payload.vessels:
                    db.add(
                        VesselRecord(
                            mmsi=v.mmsi,
                            imo=v.imo,
                            name=v.name,
                            vessel_class=v.vessel_class,
                            flag=v.flag,
                            lat=v.lat,
                            lon=v.lon,
                            speed_knots=v.speed_knots,
                            heading=v.heading,
                            draft_m=v.draft_m,
                            destination=v.destination,
                            status=v.status,
                            is_sanctioned=v.is_sanctioned,
                            dwt=v.dwt,
                            barrel_capacity=v.barrel_capacity,
                            ais_gap_hours=v.ais_gap_hours,
                            last_seen=v.last_seen,
                            source=v.source,
                        )
                    )

                db.execute(delete(DailyTransitRecord))
                for d in maritime_payload.daily_transits:
                    db.add(
                        DailyTransitRecord(
                            transit_date=d.transit_date,
                            outbound_laden_count=d.outbound_laden_count,
                            inbound_ballast_count=d.inbound_ballast_count,
                            vlcc_count=d.vlcc_count,
                            suezmax_count=d.suezmax_count,
                            aframax_count=d.aframax_count,
                            outbound_tonnage_mt=d.outbound_tonnage_mt,
                            outbound_barrels_mbbl=d.outbound_barrels_mbbl,
                            avg_speed_knots=d.avg_speed_knots,
                            loitering_count=d.loitering_count,
                            ais_gap_count=d.ais_gap_count,
                            congestion_index=d.congestion_index,
                            source=d.source,
                        )
                    )

                db.execute(delete(AisGapEventRecord))
                for g in maritime_payload.ais_gaps:
                    db.add(
                        AisGapEventRecord(
                            vessel_mmsi=g.vessel_mmsi,
                            vessel_name=g.vessel_name,
                            vessel_class=g.vessel_class,
                            start_time=g.start_time,
                            end_time=g.end_time,
                            duration_hours=g.duration_hours,
                            last_lat=g.last_lat,
                            last_lon=g.last_lon,
                            reappeared_lat=g.reappeared_lat,
                            reappeared_lon=g.reappeared_lon,
                            in_corridor=g.in_corridor,
                            is_sanctioned=g.is_sanctioned,
                            severity=g.severity,
                            source=g.source,
                        )
                    )

                db.execute(delete(OilCandleRecord))
                seen_candle_keys: set[tuple[str, str, datetime]] = set()
                for (_, _), candles in market_map.items():
                    for c in candles:
                        key = (c.symbol, c.interval, c.timestamp)
                        if key in seen_candle_keys:
                            continue
                        seen_candle_keys.add(key)
                        db.add(
                            OilCandleRecord(
                                symbol=c.symbol,
                                interval=c.interval,
                                timestamp=c.timestamp,
                                open=c.open,
                                high=c.high,
                                low=c.low,
                                close=c.close,
                                volume=c.volume,
                                source=c.source,
                            )
                        )

                db.add(
                    SignalSnapshotRecord(
                        computed_at=datetime.now(timezone.utc),
                        supply_shock_score=signal_out.supply_shock_score,
                        flow_delta_7d_vs_30d_pct=signal_out.flow_metrics.flow_delta_7d_vs_30d_pct,
                        congestion_index=signal_out.congestion_metrics.congestion_index,
                        dark_fleet_spike_score=signal_out.dark_fleet_metrics.dark_fleet_spike_score,
                        brent_bias=signal_out.brent_bias,
                        wti_bias=signal_out.wti_bias,
                        predicted_24h_brent_pct=signal_out.predicted_24h_brent_pct,
                        predicted_72h_brent_pct=signal_out.predicted_72h_brent_pct,
                        confidence_low_pct=signal_out.confidence_low_pct,
                        confidence_high_pct=signal_out.confidence_high_pct,
                        backtest_accuracy_pct=signal_out.backtest_accuracy_pct,
                    )
                )
                db.commit()

            self.cached_signal = signal_out
            self.last_refreshed = datetime.now(timezone.utc)
            logger.info(
                "Ingested %d vessels, %d transits, %d AIS gaps | Supply Shock=%.1f (%s)",
                len(maritime_payload.vessels),
                len(maritime_payload.daily_transits),
                len(maritime_payload.ais_gaps),
                signal_out.supply_shock_score,
                signal_out.brent_bias,
            )
            return signal_out

    def get_vessels_from_db(
        self, status: str | None = None, vessel_class: str | None = None
    ) -> list[VesselSnapshot]:
        with SessionLocal() as db:
            stmt = select(VesselRecord)
            if status and status != "all":
                stmt = stmt.where(VesselRecord.status == status)
            if vessel_class and vessel_class != "all":
                stmt = stmt.where(VesselRecord.vessel_class == vessel_class)
            rows = db.scalars(stmt).all()
            return [
                VesselSnapshot(
                    mmsi=r.mmsi,
                    imo=r.imo,
                    name=r.name,
                    vessel_class=r.vessel_class,  # type: ignore[arg-type]
                    flag=r.flag,
                    lat=r.lat,
                    lon=r.lon,
                    speed_knots=r.speed_knots,
                    heading=r.heading,
                    draft_m=r.draft_m,
                    destination=r.destination,
                    status=r.status,  # type: ignore[arg-type]
                    is_sanctioned=r.is_sanctioned,
                    dwt=r.dwt,
                    barrel_capacity=r.barrel_capacity,
                    ais_gap_hours=r.ais_gap_hours,
                    last_seen=r.last_seen,
                    source=r.source,
                )
                for r in rows
            ]

    def get_ais_gaps_from_db(self, mmsi: str | None = None) -> list[AisGapRecord]:
        with SessionLocal() as db:
            stmt = select(AisGapEventRecord).order_by(AisGapEventRecord.start_time.desc())
            if mmsi:
                stmt = stmt.where(AisGapEventRecord.vessel_mmsi == mmsi)
            rows = db.scalars(stmt).all()
            return [
                AisGapRecord(
                    vessel_mmsi=r.vessel_mmsi,
                    vessel_name=r.vessel_name,
                    vessel_class=r.vessel_class,  # type: ignore[arg-type]
                    start_time=r.start_time,
                    end_time=r.end_time,
                    duration_hours=r.duration_hours,
                    last_lat=r.last_lat,
                    last_lon=r.last_lon,
                    reappeared_lat=r.reappeared_lat,
                    reappeared_lon=r.reappeared_lon,
                    in_corridor=r.in_corridor,
                    is_sanctioned=r.is_sanctioned,
                    severity=r.severity,  # type: ignore[arg-type]
                    source=r.source,
                )
                for r in rows
            ]

    def get_daily_transits_from_db(self) -> list[DailyTransitPoint]:
        with SessionLocal() as db:
            rows = db.scalars(select(DailyTransitRecord).order_by(DailyTransitRecord.transit_date.asc())).all()
            return [
                DailyTransitPoint(
                    transit_date=r.transit_date,
                    outbound_laden_count=r.outbound_laden_count,
                    inbound_ballast_count=r.inbound_ballast_count,
                    vlcc_count=r.vlcc_count,
                    suezmax_count=r.suezmax_count,
                    aframax_count=r.aframax_count,
                    outbound_tonnage_mt=r.outbound_tonnage_mt,
                    outbound_barrels_mbbl=r.outbound_barrels_mbbl,
                    avg_speed_knots=r.avg_speed_knots,
                    loitering_count=r.loitering_count,
                    ais_gap_count=r.ais_gap_count,
                    congestion_index=r.congestion_index,
                    source=r.source,
                )
                for r in rows
            ]

    def get_candles_from_db(self, symbol: OilSymbol, interval: CandleInterval = "1d") -> list[OilCandle]:
        with SessionLocal() as db:
            rows = db.scalars(
                select(OilCandleRecord)
                .where(OilCandleRecord.symbol == symbol, OilCandleRecord.interval == interval)
                .order_by(OilCandleRecord.timestamp.asc())
            ).all()
            return [
                OilCandle(
                    symbol=r.symbol,  # type: ignore[arg-type]
                    interval=r.interval,  # type: ignore[arg-type]
                    timestamp=r.timestamp,
                    open=r.open,
                    high=r.high,
                    low=r.low,
                    close=r.close,
                    volume=r.volume,
                    source=r.source,
                )
                for r in rows
            ]

    async def get_signal(self) -> SignalAnalysisOutput:
        if self.cached_signal is None:
            return await self.ingest_and_recompute()
        return self.cached_signal

    def get_all_adapter_health(self) -> list[AdapterHealth]:
        return self.maritime_manager.get_health() + self.market_manager.get_health()


data_service = HormuzDataService()

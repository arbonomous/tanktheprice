"""APScheduler periodic ingestion job for maritime and crude oil feeds."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.config import settings
from backend.state import data_service

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def _scheduled_refresh() -> None:
    try:
        await data_service.ingest_and_recompute()
    except Exception as exc:
        logger.error("Scheduled HormuzFlow refresh failed: %s", exc)


def start_scheduler() -> None:
    if not scheduler.running:
        scheduler.add_job(
            _scheduled_refresh,
            "interval",
            seconds=max(60, settings.refresh_interval_seconds),
            id="hormuzflow_periodic_refresh",
            replace_existing=True,
        )
        scheduler.start()
        logger.info("APScheduler started (interval=%ds)", settings.refresh_interval_seconds)


def stop_scheduler() -> None:
    if scheduler.running:
        scheduler.shutdown(wait=False)

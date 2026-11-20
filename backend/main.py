"""HormuzFlow FastAPI application entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers.api import router as api_router
from backend.scheduler import start_scheduler, stop_scheduler
from backend.state import data_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    await data_service.ingest_and_recompute(days=45)
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(
    title="HormuzFlow Maritime Intelligence & Oil Signal API",
    version="1.0.0",
    description="Real-time Strait of Hormuz tanker chokepoint telemetry and Brent/WTI crude oil price-swing signal engine.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "hormuzflow-api"}

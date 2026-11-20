"""CLI entrypoint to initialize SQLite database and seed HormuzFlow feeds."""

from __future__ import annotations

import asyncio
import logging

from backend.database import init_db
from backend.state import data_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


async def main() -> None:
    init_db()
    sig = await data_service.ingest_and_recompute(days=45)
    print(
        f"Seeded HormuzFlow DB successfully | "
        f"Supply Shock: {sig.supply_shock_score:+.1f} | "
        f"Brent Bias: {sig.brent_bias} ({sig.predicted_72h_brent_pct:+.2f}% 72h) | "
        f"Backtest Accuracy: {sig.backtest_accuracy_pct:.1f}% | "
        f"Maritime Source: {data_service.maritime_source} | "
        f"Market Source: {data_service.market_source}"
    )


if __name__ == "__main__":
    asyncio.run(main())

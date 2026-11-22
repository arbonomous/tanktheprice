# AGENTS.md — HormuzFlow Architecture & Developer Guide

**HormuzFlow** is a full-stack maritime intelligence and crude oil price-swing prediction terminal tracking oil tankers transiting the Strait of Hormuz (`24.0°N–28.0°N, 55.0°E–58.5°E`) and correlating chokepoint anomalies with Brent (`BZ=F`) and WTI (`CL=F`) crude oil price movements.

---

## 1. Repository Architecture

```text
tanktheprice/
├── .env.example                 # Documented environment variables & optional API keys
├── .env.local                   # Local runtime configuration (gitignored)
├── AGENTS.md                    # This architecture & onboarding guide
├── scripts/
│   ├── dev.sh                   # Starts FastAPI (:8000) & Next.js (:3000) concurrently
│   └── build_live_pages.py      # Generates docs/data/live_snapshot.json & docs/data/paper_trades.json
├── docs/                        # GitHub Pages live terminal (zero-server static deployment)
│   ├── index.html               # Standalone terminal with 20s live AIS polling, 2y backtest & paper ledger
│   └── data/                    # Auto-refreshed live_snapshot.json & persistent paper_trades.json
├── data/
│   └── hormuzflow.db            # SQLite database (auto-created on first boot/seed)
├── services/                    # Core Python domain packages
│   ├── alerts.py                # Live alert feed builder + optional Discord/Telegram webhook dispatcher
│   ├── maritime_feed/           # Adapter pattern for AIS & chokepoint transit feeds
│   │   ├── base.py              # MaritimeAdapter ABC + VesselSnapshot / DailyTransitPoint / AisGapRecord
│   │   ├── hormuz_now.py        # Primary free live feed (https://hormuz.now /api/snapshot, /api/daily.json, /api/portwatch, /status.json, /api/areas, /api/ports)
│   │   ├── imf_portwatch.py     # Free IMF PortWatch ArcGIS FeatureServer baseline tanker counts
│   │   ├── aisstream.py         # Optional free WebSocket AIS (AISStream.io)
│   │   ├── straits_live.py      # Optional paid AIS (/api/v1/transits, /api/v1/ais-gaps, /api/v1/sanctioned-vessels)
│   │   ├── datalastic.py        # Optional paid AIS (vessel_inradius around 26.566°N, 56.25°E, r=45 NM)
│   │   ├── marinetraffic.py     # Optional paid AIS (ExportVessels bounding-box endpoint)
│   │   ├── simulator.py         # Deterministic Hormuz traffic, dark-fleet & geopolitical choke simulator
│   │   └── manager.py           # Priority orchestrator + zero-key fallback + adapter health registry
│   ├── market_feed/             # Adapter pattern for Brent (BZ=F), WTI (CL=F) & tradable ETFs/tankers
│   │   ├── base.py              # MarketAdapter ABC + OilCandle schema
│   │   ├── yfinance_adapter.py  # Free zero-key daily & hourly OHLCV via yfinance
│   │   ├── equities.py          # 2-year OHLCV + ATR(14) + SMA(20) for BNO, USO, FRO, DHT, STNG, BZ=F, CL=F
│   │   ├── alphavantage_adapter.py # Optional Alpha Vantage commodity adapter
│   │   ├── simulator.py         # Correlated fallback candle simulator if upstream is unreachable
│   │   └── manager.py           # Market orchestrator + adapter health
│   └── signal_engine/           # Quantitative maritime-to-crude signal modeling
│       ├── geometry.py          # Strait bbox, TSS outbound/inbound polygons, anchorages, dark corridor
│       ├── flow_metrics.py      # Net Outbound Laden Flow (heading 090°-160°, draft > 12m, 7d vs 30d)
│       ├── congestion.py        # Chokepoint Congestion & Loitering Index (speed < 3kn outside anchorages)
│       ├── dark_fleet.py        # Dark-Fleet / AIS Gap Spike Score in 25.5°N–27.0°N, 55.8°E–57.0°E
│       ├── predictor.py         # Composite Supply Shock Score (-100..+100), GBR + Z-score predictor, backtester
│       ├── backtester.py        # Zero-lookahead 2-year walk-forward trade-level backtester (10 bps RT slippage) + live 5-ticker tickets
│       ├── paper_trader.py      # Persistent $100k Balanced Swing Desk automated paper-trading ledger
│       └── stress_test.py       # Interactive VLCC drop & AIS spoofing price-impact elasticity simulator
├── backend/                     # FastAPI + SQLAlchemy + APScheduler
│   ├── main.py                  # FastAPI entrypoint, CORS, lifespan startup & APScheduler hooks
│   ├── config.py                # Pydantic settings reading .env.local
│   ├── database.py              # SQLite engine & SessionLocal
│   ├── models.py                # ORM tables (vessels, daily_transits, ais_gap_events, oil_candles, signal_snapshots)
│   ├── schemas.py               # REST API request/response contracts
│   ├── state.py                 # HormuzDataService (ingestion, persistence, cached signal evaluation)
│   ├── scheduler.py             # APScheduler periodic refresh worker
│   ├── seed.py                  # CLI script (`python -m backend.seed`)
│   ├── routers/api.py           # REST API endpoints under /api/*
│   └── tests/test_hormuzflow.py # Pytest suite
└── frontend/                    # Next.js (App Router) + TypeScript + Tailwind CSS v4 + Shadcn/UI
    └── src/
        ├── app/                 # layout.tsx, page.tsx, globals.css (#0B0F19 terminal palette)
        ├── lib/                 # api.ts, types.ts, utils.ts, hormuz-geo.ts (embedded Hormuz GeoJSON)
        └── components/          # KpiTickerBar, HormuzMap, VesselDrawer, CorrelationChart, SignalAnalytics, StressTestPanel, AnomalyFeedTable
```

---

## 2. Database Schema (SQLite via SQLAlchemy)

| Table | Purpose | Key Columns |
| --- | --- | --- |
| `vessels` | Latest live tanker telemetry inside Strait of Hormuz | `mmsi` (unique), `imo`, `name`, `vessel_class`, `flag`, `lat`, `lon`, `speed_knots`, `heading`, `draft_m`, `destination`, `status`, `is_sanctioned`, `dwt`, `barrel_capacity`, `ais_gap_hours`, `source` |
| `daily_transits` | Historical daily chokepoint transit counts & tonnage | `transit_date` (unique), `outbound_laden_count`, `inbound_ballast_count`, `vlcc_count`, `suezmax_count`, `aframax_count`, `outbound_tonnage_mt`, `outbound_barrels_mbbl`, `avg_speed_knots`, `loitering_count`, `ais_gap_count`, `congestion_index` |
| `ais_gap_events` | Active and resolved dark-ship transponder blackouts | `vessel_mmsi`, `vessel_name`, `vessel_class`, `start_time`, `end_time`, `duration_hours`, `last_lat`, `last_lon`, `in_corridor`, `is_sanctioned`, `severity` |
| `oil_candles` | Daily (`1d`) & intraday (`1h`) Brent (`BZ=F`) and WTI (`CL=F`) OHLCV | `(symbol, interval, timestamp)` unique, `open`, `high`, `low`, `close`, `volume`, `source` |
| `signal_snapshots` | Historical log of computed composite signal evaluations | `computed_at`, `supply_shock_score`, `flow_delta_7d_vs_30d_pct`, `congestion_index`, `dark_fleet_spike_score`, `brent_bias`, `predicted_72h_brent_pct`, `backtest_accuracy_pct` |

---

## 3. REST API Endpoints (`http://localhost:8000`)

- `GET /health` — Service health probe.
- `GET /api/dashboard/summary` — Top KPI ticker metrics (Brent/WTI quotes, 24h outbound laden count & Mbbl, 7d vs 30d flow delta, AIS-dark count, Supply Shock Score, 24h–72h bias, adapter statuses).
- `GET /api/vessels?status=&vessel_class=` — Filterable live tanker positions.
- `GET /api/vessels/{mmsi}` — Detailed vessel telemetry, corridor flags (`in_dark_corridor`, `in_tss_lane`, `is_congestion_loitering`), and AIS gap history.
- `GET /api/ais-gaps` — Active and historical AIS blackout events.
- `GET /api/market/candles?symbol=BZ=F&interval=1d` — OHLCV oil candles joined with daily tanker signal overlays and detected divergence zones.
- `GET /api/signals/overview` — Full quantitative engine output (flow/congestion/dark-fleet sub-metrics, 1d/3d/7d lag correlations, walk-forward backtest accuracy & series, daily signals).
- `POST /api/simulation/stress-test` — Calculates Brent & WTI price impact and 7-day curve for custom VLCC drop %, AIS spoofing multiplier, congestion surge %, and duration.
- `GET /api/adapters/status` / `POST /api/adapters/refresh` / `POST /api/adapters/mode` — Inspect feed health, trigger manual refresh, or switch between `auto` and `simulator` mode.

---

## 4. Quantitative Signal Formulas

1. **Net Outbound Laden Flow (`services/signal_engine/flow_metrics.py`)**
   - Criteria: `90° <= heading <= 160°` and `draft_m > 12.0m`.
   - Compares 7-day rolling average outbound laden tanker count & Mbbl/d against 30-day baseline to produce `flow_delta_7d_vs_30d_pct` and `flow_zscore`.
2. **Chokepoint Congestion & Loitering Index (`services/signal_engine/congestion.py`)**
   - Flags tankers with `speed_knots < 3.0` near Fujairah, Bandar Abbas, or inside TSS lanes **excluding** designated anchorage polygons.
3. **Dark-Fleet / AIS Gap Spike Score (`services/signal_engine/dark_fleet.py`)**
   - Counts active transponder blackouts inside `25.5°N–27.0°N, 55.8°E–57.0°E`, weights sanctioned vessels and blackout duration, and computes 30-day rolling z-score.
4. **Composite Hormuz Supply Shock Score (`-100` to `+100`) & Predictor (`services/signal_engine/predictor.py`)**
   - Weighted anomaly score: `(-0.50 * flow_z + 0.25 * cong_z + 0.25 * dark_z) * 34`, clamped to `[-100, +100]`.
   - Expanding-window walk-forward `GradientBoostingRegressor` blended with z-score anomaly priors generates out-of-sample 24h & 72h Brent/WTI forecasts, 80% confidence interval, rolling lag correlations (1d/3d/7d), and directional hit-rate backtest metrics.

---

## 5. Plugging In Live API Keys (Zero-Key to Production Upgrade)

HormuzFlow works out of the box with zero API keys (`FEED_MODE=auto` pulls live Brent/WTI via `yfinance`, queries free `Hormuz.now` + `IMF PortWatch` feeds, and automatically merges the deterministic 45-day Strait of Hormuz simulator when upstream AIS endpoints are unavailable).

To upgrade to high-resolution commercial AIS or Alpha Vantage oil data:

1. Open `.env.local` (copied from `.env.example`) — or add Repository Secrets in GitHub Settings → Secrets and variables → Actions for the automated GitHub Pages refresh workflow (`.github/workflows/refresh-live-data.yml`, running every 2 hours during US market hours Mon–Fri 13:00–21:00 UTC and every 6 hours off-hours/weekends):
   ```env
   FEED_MODE=auto
   AISSTREAM_API_KEY=your_free_aisstream_io_key
   STRAITS_LIVE_API_KEY=your_straits_live_key
   DATALASTIC_API_KEY=your_datalastic_key
   MARINETRAFFIC_API_KEY=your_marinetraffic_key
   ALPHAVANTAGE_API_KEY=your_alphavantage_key
   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   ```
2. Restart the FastAPI server or click **REFRESH** in the top-right KPI bar (or manually run the **Refresh Live HormuzFlow Data** GitHub Action).
3. Click **FEEDS** in the header to verify each adapter flips from `STANDBY NO KEY` to `LIVE`:
   - **Priority order (Maritime):** `Straits.live` → `Datalastic` → `MarineTraffic` → `AISStream.io` (free live WebSocket AIS) → `Hormuz.now` / `IMF PortWatch` → `HormuzSimulator` fallback.
   - **Priority order (Oil Market):** `Alpha Vantage` (if key set, daily) → `yfinance` (`BZ=F` & `CL=F`, daily + hourly) → `MarketSimulator` fallback.

---

## 6. Running & Testing Locally

```bash
# 1. Seed SQLite database
PYTHONPATH=. .venv/bin/python -m backend.seed

# 2. Run backend pytest suite
PYTHONPATH=. .venv/bin/pytest -v backend/tests/test_hormuzflow.py

# 3. Start backend & frontend (or run ./scripts/dev.sh)
PYTHONPATH=. .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
cd frontend && npm run dev
```

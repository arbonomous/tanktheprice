# HormuzFlow

**Real-time Strait of Hormuz Maritime Intelligence & Crude Oil Price-Swing Prediction Terminal**

Tracks crude/product oil tankers transiting the Strait of Hormuz (`24.0°N–28.0°N, 55.0°E–58.5°E`) and correlates outbound laden flow drops, TSS congestion/loitering, and AIS-dark corridor anomalies with Brent (`BZ=F`) and WTI (`CL=F`) crude oil price movements.

## Live Demo & One-Click Cloud Hosting

- **Live Web Terminal (GitHub Pages):** https://arbonomous.github.io/tanktheprice/
- **Deploy Full-Stack (FastAPI + Next.js) to Render:**
  [![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/arbonomous/tanktheprice)
- **Deploy Frontend to Vercel:**
  [![Deploy with Vercel](https://vercel.com/button)](https://vercel.com/new/clone?repository-url=https%3A%2F%2Fgithub.com%2Farbonomous%2Ftanktheprice&root-directory=frontend&env=NEXT_PUBLIC_API_URL)

## Architecture & API Keys

See [`AGENTS.md`](./AGENTS.md) for the full architecture diagram, SQLite schema, quantitative signal formulas, and instructions for plugging in optional commercial API keys (`STRAITS_LIVE_API_KEY`, `DATALASTIC_API_KEY`, `MARINETRAFFIC_API_KEY`, `ALPHAVANTAGE_API_KEY`).

## Quick Local Run

```bash
./scripts/dev.sh
```

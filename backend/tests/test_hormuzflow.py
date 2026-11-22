"""Automated pytest suite verifying HormuzFlow adapters, signal engine, stress test, and FastAPI routes."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.main import app
from backend.state import data_service
from services.maritime_feed.manager import MaritimeFeedManager
from services.maritime_feed.simulator import HormuzSimulator
from services.market_feed.simulator import MarketSimulator
from services.signal_engine.geometry import (
    is_congestion_loitering,
    is_in_dark_corridor,
    is_in_designated_anchorage,
    is_outbound_laden,
)
from services.signal_engine.predictor import run_signal_engine
from services.signal_engine.stress_test import run_stress_test


def test_geometry_rules() -> None:
    assert is_outbound_laden(120.0, 17.5) is True
    assert is_outbound_laden(300.0, 17.5) is False
    assert is_outbound_laden(120.0, 9.5) is False

    assert is_in_dark_corridor(26.2, 56.4) is True
    assert is_in_dark_corridor(24.5, 58.0) is False

    # Inside Fujairah designated anchorage should NOT count as abnormal loitering
    assert is_in_designated_anchorage(25.15, 56.46) is True
    assert is_congestion_loitering(25.15, 56.46, 0.8) is False
    # Outside anchorage near Fujairah approach at <3 kn SHOULD flag loitering
    assert is_congestion_loitering(25.48, 56.75, 1.2) is True
    # Moving at 12 kn should NOT flag loitering
    assert is_congestion_loitering(25.48, 56.75, 12.0) is False


def test_signal_engine_and_backtest_bounds() -> None:
    sim_m = HormuzSimulator(seed=202604)
    sim_o = MarketSimulator(seed=202604)
    payload = sim_m.generate_sync(days=45)
    brent = sim_o.generate_sync("BZ=F", "1d", days=45)
    wti = sim_o.generate_sync("CL=F", "1d", days=45)

    out = run_signal_engine(
        vessels=payload.vessels,
        ais_gaps=payload.ais_gaps,
        daily_transits=payload.daily_transits,
        brent_candles=brent,
        wti_candles=wti,
    )

    assert -100.0 <= out.supply_shock_score <= 100.0
    assert out.brent_bias in ("BULLISH", "BEARISH", "NEUTRAL")
    assert out.wti_bias in ("BULLISH", "BEARISH", "NEUTRAL")
    assert len(out.lag_correlations) == 3
    assert [lc.lag_days for lc in out.lag_correlations] == [1, 3, 7]
    assert out.backtest_sample_size > 15
    assert 0.0 <= out.backtest_accuracy_pct <= 100.0
    assert len(out.divergence_zones) >= 1
    assert len(out.daily_signals) == 45


def test_stress_test_monotonicity() -> None:
    r15 = run_stress_test(82.0, 77.5, 25.0, 28.0, vlcc_drop_pct=15.0, ais_spoofing_multiplier=1.5)
    r30 = run_stress_test(82.0, 77.5, 25.0, 28.0, vlcc_drop_pct=30.0, ais_spoofing_multiplier=2.0)
    r50 = run_stress_test(82.0, 77.5, 25.0, 28.0, vlcc_drop_pct=50.0, ais_spoofing_multiplier=3.5)

    assert r15.brent_delta_usd < r30.brent_delta_usd < r50.brent_delta_usd
    assert r15.wti_delta_usd < r30.wti_delta_usd < r50.wti_delta_usd
    assert r50.projected_supply_shock_score >= r30.projected_supply_shock_score >= r15.projected_supply_shock_score
    assert len(r30.projection_curve) == 8


def test_adapter_manager_fallback_zero_key() -> None:
    mgr = MaritimeFeedManager(feed_mode="simulator")
    payload = asyncio.run(mgr.fetch_all(days=30))
    assert len(payload.vessels) >= 50
    assert len(payload.daily_transits) == 30
    health = {h.name: h for h in mgr.get_health()}
    assert health["straits_live"].status == "STANDBY_NO_KEY"
    assert health["datalastic"].status == "STANDBY_NO_KEY"
    assert health["hormuz_simulator"].active is True


def test_fastapi_endpoints() -> None:
    # Force deterministic simulator mode for fast offline test execution
    data_service.set_feed_mode("simulator")
    with TestClient(app) as client:
        r_health = client.get("/health")
        assert r_health.status_code == 200

        r_sum = client.get("/api/dashboard/summary")
        assert r_sum.status_code == 200
        summary = r_sum.json()
        assert summary["brent"]["symbol"] == "BZ=F"
        assert summary["wti"]["symbol"] == "CL=F"
        assert -100.0 <= summary["supply_shock_score"] <= 100.0
        assert summary["outbound_laden_24h"] > 0

        r_vessels = client.get("/api/vessels")
        assert r_vessels.status_code == 200
        vessels = r_vessels.json()
        assert len(vessels) >= 50

        first_mmsi = vessels[0]["mmsi"]
        r_detail = client.get(f"/api/vessels/{first_mmsi}")
        assert r_detail.status_code == 200
        assert r_detail.json()["vessel"]["mmsi"] == first_mmsi

        r_candles = client.get("/api/market/candles", params={"symbol": "BZ=F", "interval": "1d"})
        assert r_candles.status_code == 200
        assert len(r_candles.json()["candles"]) >= 30

        r_sig = client.get("/api/signals/overview")
        assert r_sig.status_code == 200
        assert len(r_sig.json()["lag_correlations"]) == 3

        r_stress = client.post(
            "/api/simulation/stress-test",
            json={"vlcc_drop_pct": 50.0, "ais_spoofing_multiplier": 3.0, "congestion_surge_pct": 60.0, "duration_days": 7},
        )
        assert r_stress.status_code == 200
        assert r_stress.json()["brent_delta_pct"] > 5.0


def test_walk_forward_backtester_and_paper_trader() -> None:
    from services.alerts import build_alert_item, format_webhook_digest
    from services.market_feed.equities import simulate_asset_universe
    from services.signal_engine.backtester import MAX_CONCURRENT_POSITIONS, run_walk_forward_backtest
    from services.signal_engine.paper_trader import _new_ledger, step_paper_portfolio

    sim_m = HormuzSimulator(seed=202611).generate_sync(days=365)
    assets = simulate_asset_universe(days=260, seed=202611)

    wf = run_walk_forward_backtest(
        asset_histories=assets,
        transits=sim_m.daily_transits,
        live_shock_override=35.0,
        live_flow_z_override=-1.4,
        live_cong_z_override=1.2,
    )
    assert wf.starting_equity == 100_000.0
    assert wf.slippage_bps_roundtrip == 10
    assert wf.max_concurrent == MAX_CONCURRENT_POSITIONS
    assert len(wf.equity_curve) > 50
    assert len(wf.live_tickets) == 5
    assert {t.ticker for t in wf.live_tickets} == {"BNO", "USO", "FRO", "DHT", "STNG"}

    # Paper-trading step 1: opens up to 3 positions on high-conviction tickets
    ledger = _new_ledger()
    ledger, alerts_1 = step_paper_portfolio(
        ledger=ledger,
        live_tickets=wf.live_tickets,
        supply_shock_score=35.0,
        brent_bias="BULLISH",
        waiting_queue_total=500,
    )
    assert len(ledger["open_positions"]) <= MAX_CONCURRENT_POSITIONS
    assert ledger["equity"] > 0
    assert len(alerts_1) >= 1

    # Paper-trading step 2: simulate severe stop-out / signal exit
    if ledger["open_positions"]:
        first_pos = ledger["open_positions"][0]
        # Force a stop hit on the first open ticker
        modified_tickets = []
        for tk in wf.live_tickets:
            if tk.ticker == first_pos["ticker"]:
                tk.price = round(first_pos["stop_price"] * (0.95 if first_pos["side"] == "LONG" else 1.05), 2)
            modified_tickets.append(tk)
        ledger, alerts_2 = step_paper_portfolio(
            ledger=ledger,
            live_tickets=modified_tickets,
            supply_shock_score=-25.0,
            brent_bias="BEARISH",
        )
        assert len(ledger["closed_trades"]) >= 1
        digest = format_webhook_digest(
            alerts_2 or [build_alert_item("OPEN", "HIGH", "Test", "Body", "BNO")],
            {"bp": 90.0, "wp": 83.0, "shock": 30.0, "bias": "BULLISH"},
        )
        assert "HormuzFlow Signal Alert" in digest


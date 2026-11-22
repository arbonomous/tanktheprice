"""Automated Balanced Swing Desk Paper-Trading Engine persisted to docs/data/paper_trades.json."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from services.alerts import build_alert_item
from services.signal_engine.backtester import (
    MAX_CONCURRENT_POSITIONS,
    MAX_HOLD_DAYS,
    MAX_POSITION_EQUITY_FRAC,
    ONE_WAY_SLIPPAGE,
    RISK_PER_TRADE_PCT,
    STARTING_EQUITY,
    LiveSignalTicket,
)


def _new_ledger() -> dict[str, Any]:
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "created_at": now_str,
        "updated_at": now_str,
        "profile": "Balanced Swing Desk ($100k · 1.5% risk · max 3 positions · ATR stops)",
        "starting_equity": STARTING_EQUITY,
        "cash": STARTING_EQUITY,
        "equity": STARTING_EQUITY,
        "realized_pnl_usd": 0.0,
        "unrealized_pnl_usd": 0.0,
        "total_return_pct": 0.0,
        "win_rate_pct": 0.0,
        "last_regime": "NEUTRAL",
        "open_positions": [],
        "closed_trades": [],
        "equity_history": [{"timestamp": now_str, "equity": STARTING_EQUITY}],
        "alerts": [],
    }


def load_paper_ledger(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "cash" in data and "open_positions" in data:
                return data
        except Exception:
            pass
    return _new_ledger()


def _trading_days_elapsed(entry_iso: str, now_date: date) -> int:
    try:
        d0 = date.fromisoformat(entry_iso[:10])
    except Exception:
        return 0
    if now_date <= d0:
        return 0
    days = 0
    cur = d0
    while cur < now_date:
        cur = date.fromordinal(cur.toordinal() + 1)
        if cur.weekday() < 5:
            days += 1
    return days


def step_paper_portfolio(
    ledger: dict[str, Any],
    live_tickets: Sequence[LiveSignalTicket],
    supply_shock_score: float,
    brent_bias: str,
    waiting_queue_total: int = 0,
    now_utc: datetime | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """
    Advance the automated paper-trading portfolio by one live evaluation step:
      1. Mark open positions to live prices & execute stop-loss / profit-target / time-stop / invalidation exits
      2. Open new high-conviction entries within the 3-position cap
      3. Record equity history & emit structured alerts
    """
    now = now_utc or datetime.now(timezone.utc)
    now_str = now.strftime("%Y-%m-%d %H:%M UTC")
    today = now.date()

    ticket_by_tkr = {t.ticker: t for t in live_tickets}
    new_alerts: list[dict[str, Any]] = []

    # Check macro regime flip alert
    prev_regime = ledger.get("last_regime", "NEUTRAL")
    if prev_regime != brent_bias and brent_bias in ("BULLISH", "BEARISH"):
        new_alerts.append(
            build_alert_item(
                kind="REGIME_FLIP",
                severity="HIGH",
                title=f"Hormuz Regime Flipped -> {brent_bias}",
                message=f"Composite Supply Shock moved to {supply_shock_score:+.1f} (prior regime: {prev_regime}).",
            )
        )
    ledger["last_regime"] = brent_bias

    if waiting_queue_total >= 450:
        new_alerts.append(
            build_alert_item(
                kind="QUEUE_SURGE",
                severity="HIGH",
                title=f"Hormuz Queue Surge ({waiting_queue_total} Ships Waiting)",
                message="Elevated vessel queuing off Gulf of Oman & Persian Gulf approaches — bullish freight & Brent risk.",
            )
        )

    # 1. Mark open positions and evaluate exit triggers
    remaining_open: list[dict[str, Any]] = []
    for pos in ledger.get("open_positions", []):
        tkr = pos["ticker"]
        tk = ticket_by_tkr.get(tkr)
        cur_px = tk.price if tk else float(pos.get("current_price", pos["entry_price"]))
        side = pos["side"]
        shares = int(pos["shares"])
        entry_px = float(pos["entry_price"])
        stop_px = float(pos["stop_price"])
        target_px = float(pos["target_price"])
        hold_days = _trading_days_elapsed(pos["opened_at"], today)

        exit_reason: str | None = None
        if side == "LONG":
            if cur_px <= stop_px:
                exit_reason = "STOP_OUT"
            elif cur_px >= target_px:
                exit_reason = "TARGET_HIT"
            elif hold_days >= MAX_HOLD_DAYS:
                exit_reason = "TIME_STOP"
            elif supply_shock_score <= -18.0:
                exit_reason = "SIGNAL_EXIT"
        else:
            if cur_px >= stop_px:
                exit_reason = "STOP_OUT"
            elif cur_px <= target_px:
                exit_reason = "TARGET_HIT"
            elif hold_days >= MAX_HOLD_DAYS:
                exit_reason = "TIME_STOP"
            elif supply_shock_score >= 20.0:
                exit_reason = "SIGNAL_EXIT"

        if exit_reason:
            exec_exit = round(cur_px * (1.0 - ONE_WAY_SLIPPAGE if side == "LONG" else 1.0 + ONE_WAY_SLIPPAGE), 2)
            pnl = (exec_exit - entry_px) * shares if side == "LONG" else (entry_px - exec_exit) * shares
            notional = float(pos["notional"])
            if side == "LONG":
                ledger["cash"] = round(float(ledger["cash"]) + exec_exit * shares, 2)
            else:
                ledger["cash"] = round(float(ledger["cash"]) + notional + pnl, 2)

            pnl_pct = (pnl / max(notional, 1.0)) * 100.0
            r_mult = pnl / max(float(pos.get("risk_usd", 1.0)), 1.0)
            closed_rec = {
                "ticker": tkr,
                "side": side,
                "opened_at": pos["opened_at"],
                "closed_at": now_str,
                "entry_price": entry_px,
                "exit_price": exec_exit,
                "shares": shares,
                "pnl_usd": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_mult, 2),
                "hold_days": hold_days,
                "exit_reason": exit_reason,
            }
            ledger["closed_trades"].insert(0, closed_rec)
            ledger["closed_trades"] = ledger["closed_trades"][:100]
            ledger["realized_pnl_usd"] = round(float(ledger.get("realized_pnl_usd", 0.0)) + pnl, 2)

            sev = "CRITICAL" if exit_reason == "STOP_OUT" else "HIGH"
            new_alerts.append(
                build_alert_item(
                    kind=exit_reason,
                    severity=sev,
                    ticker=tkr,
                    title=f"Paper {exit_reason.replace('_', ' ')} — {side} {tkr}",
                    message=f"Closed {shares} sh @ ${exec_exit:.2f} (entry ${entry_px:.2f}) | P&L {pnl:+.2f} ({pnl_pct:+.2f}%).",
                )
            )
        else:
            unreal = (cur_px - entry_px) * shares if side == "LONG" else (entry_px - cur_px) * shares
            unreal_pct = (unreal / max(float(pos["notional"]), 1.0)) * 100.0
            pos["current_price"] = round(cur_px, 2)
            pos["unrealized_pnl_usd"] = round(unreal, 2)
            pos["unrealized_pnl_pct"] = round(unreal_pct, 2)
            pos["hold_days"] = hold_days
            remaining_open.append(pos)

    ledger["open_positions"] = remaining_open

    # Compute live mark-to-market equity before opening new positions
    def _calc_equity() -> tuple[float, float]:
        unreal_total = 0.0
        pos_val = 0.0
        for p in ledger["open_positions"]:
            c_px = float(p["current_price"])
            sh = int(p["shares"])
            if p["side"] == "LONG":
                pos_val += c_px * sh
                unreal_total += (c_px - float(p["entry_price"])) * sh
            else:
                u = (float(p["entry_price"]) - c_px) * sh
                pos_val += float(p["notional"]) + u
                unreal_total += u
        return round(float(ledger["cash"]) + pos_val, 2), round(unreal_total, 2)

    cur_equity, _ = _calc_equity()

    # 2. Open new paper positions for high-conviction tickets up to MAX_CONCURRENT_POSITIONS
    open_tickers = {p["ticker"] for p in ledger["open_positions"]}
    candidates = [t for t in live_tickets if t.stance in ("LONG", "SHORT") and t.ticker not in open_tickers]
    candidates.sort(key=lambda x: x.conviction, reverse=True)

    for tk in candidates:
        if len(ledger["open_positions"]) >= MAX_CONCURRENT_POSITIONS:
            break
        exec_entry = round(
            tk.entry_price * (1.0 + ONE_WAY_SLIPPAGE if tk.stance == "LONG" else 1.0 - ONE_WAY_SLIPPAGE), 2
        )
        stop_dist = max(0.05, abs(exec_entry - tk.stop_price))
        risk_budget = cur_equity * RISK_PER_TRADE_PCT
        raw_shares = int(risk_budget / stop_dist)
        max_notional = min(float(ledger["cash"]) * 0.96, cur_equity * MAX_POSITION_EQUITY_FRAC)
        shares = min(raw_shares, int(max_notional / max(exec_entry, 0.01)))
        if shares <= 0:
            continue

        notional = round(shares * exec_entry, 2)
        ledger["cash"] = round(float(ledger["cash"]) - notional, 2)
        pos_obj = {
            "ticker": tk.ticker,
            "name": tk.name,
            "side": tk.stance,
            "opened_at": now_str,
            "entry_price": exec_entry,
            "current_price": tk.price,
            "stop_price": tk.stop_price,
            "target_price": tk.target_price,
            "shares": shares,
            "notional": notional,
            "risk_usd": round(shares * stop_dist, 2),
            "conviction": tk.conviction,
            "rationale": tk.rationale,
            "unrealized_pnl_usd": round((tk.price - exec_entry) * shares if tk.stance == "LONG" else (exec_entry - tk.price) * shares, 2),
            "unrealized_pnl_pct": round((((tk.price - exec_entry) if tk.stance == "LONG" else (exec_entry - tk.price)) / max(exec_entry, 0.01)) * 100.0, 2),
            "hold_days": 0,
        }
        ledger["open_positions"].append(pos_obj)
        new_alerts.append(
            build_alert_item(
                kind="OPEN",
                severity="HIGH",
                ticker=tk.ticker,
                title=f"Opened Paper {tk.stance} {tk.ticker} ({tk.conviction:.0f}/100)",
                message=f"Entry ${exec_entry:.2f} × {shares} sh (${notional:,.0f}) | Target ${tk.target_price:.2f} | Stop ${tk.stop_price:.2f}.",
            )
        )

    # 3. Finalize ledger metrics & equity curve
    final_equity, unreal_total = _calc_equity()
    ledger["equity"] = final_equity
    ledger["unrealized_pnl_usd"] = unreal_total
    ledger["total_return_pct"] = round(((final_equity / STARTING_EQUITY) - 1.0) * 100.0, 2)
    closed = ledger.get("closed_trades", [])
    ledger["win_rate_pct"] = round((sum(1 for c in closed if c["pnl_usd"] > 0) / len(closed) * 100.0) if closed else 0.0, 1)
    ledger["updated_at"] = now_str

    eq_hist = ledger.get("equity_history", [])
    if not eq_hist or eq_hist[-1]["timestamp"] != now_str:
        eq_hist.append({"timestamp": now_str, "equity": final_equity})
        ledger["equity_history"] = eq_hist[-240:]

    if new_alerts:
        ledger["alerts"] = (new_alerts + ledger.get("alerts", []))[:40]
    elif not ledger.get("alerts"):
        ledger["alerts"] = [
            build_alert_item(
                kind="SYSTEM",
                severity="INFO",
                title="Balanced Swing Paper Desk Active",
                message=f"Tracking BNO, USO, FRO, DHT, STNG ($100k capital · 1.5% risk/trade · Shock {supply_shock_score:+.1f}).",
            )
        ]

    return ledger, new_alerts


def save_paper_ledger(path: Path, ledger: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, indent=2), encoding="utf-8")

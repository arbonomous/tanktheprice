"""Alert generation and optional zero-cost Discord / Telegram webhook delivery."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)


def build_alert_item(
    kind: str,
    severity: str,
    title: str,
    message: str,
    ticker: str | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{kind}-{ticker or 'SYS'}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M')}",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "kind": kind,
        "severity": severity,  # INFO | HIGH | CRITICAL
        "ticker": ticker,
        "title": title,
        "message": message,
    }


def format_webhook_digest(alerts: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    lines = [
        f"🚢 **HormuzFlow Signal Alert** ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        f"• Brent: **${summary.get('bp', 0):.2f}** | WTI: **${summary.get('wp', 0):.2f}** | Shock: **{summary.get('shock', 0):+.1f} ({summary.get('bias', 'NEUTRAL')})**",
        "",
    ]
    for a in alerts[:6]:
        icon = "🚨" if a["severity"] == "CRITICAL" else ("⚡" if a["severity"] == "HIGH" else "ℹ️")
        tkr = f"[{a['ticker']}] " if a.get("ticker") else ""
        lines.append(f"{icon} **{tkr}{a['title']}** — {a['message']}")
    lines.append("")
    lines.append("Dashboard: https://arbonomous.github.io/tanktheprice/")
    return "\n".join(lines)


async def dispatch_webhook_alerts(
    alerts: list[dict[str, Any]],
    summary: dict[str, Any],
    discord_webhook_url: str | None = None,
    telegram_bot_token: str | None = None,
    telegram_chat_id: str | None = None,
) -> dict[str, str]:
    """Send high-conviction trade/regime alerts to Discord and/or Telegram if secrets are configured."""
    status: dict[str, str] = {"discord": "STANDBY_NO_SECRET", "telegram": "STANDBY_NO_SECRET"}
    actionable = [a for a in alerts if a.get("severity") in ("HIGH", "CRITICAL")]
    if not actionable:
        return status

    discord_url = (discord_webhook_url if discord_webhook_url is not None else os.getenv("DISCORD_WEBHOOK_URL", "")).strip()
    tg_token = (telegram_bot_token if telegram_bot_token is not None else os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    tg_chat = (telegram_chat_id if telegram_chat_id is not None else os.getenv("TELEGRAM_CHAT_ID", "")).strip()

    if not discord_url and not (tg_token and tg_chat):
        return status

    body = format_webhook_digest(actionable, summary)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            if discord_url:
                try:
                    r = await client.post(discord_url, json={"content": body})
                    status["discord"] = "SENT" if r.status_code < 300 else f"HTTP_{r.status_code}"
                except Exception as exc:
                    logger.warning("Discord webhook failed: %s", exc)
                    status["discord"] = "ERROR"

            if tg_token and tg_chat:
                try:
                    r = await client.post(
                        f"https://api.telegram.org/bot{tg_token}/sendMessage",
                        json={"chat_id": tg_chat, "text": body, "parse_mode": "Markdown"},
                    )
                    status["telegram"] = "SENT" if r.status_code < 300 else f"HTTP_{r.status_code}"
                except Exception as exc:
                    logger.warning("Telegram alert failed: %s", exc)
                    status["telegram"] = "ERROR"
    except Exception as exc:
        logger.warning("Alert HTTP client unavailable: %s", exc)

    return status

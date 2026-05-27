"""
Aurentis AI — Discord webhook alerts.
Sends rich embeds on trade open, close, and circuit breaker events.
"""
import logging
import threading
import time
from typing import Optional

import requests

log = logging.getLogger("aurentis.alerts")


class DiscordAlerter:
    def __init__(self, webhook_url: str, enabled: bool = True):
        self._url     = webhook_url
        self._enabled = enabled and bool(webhook_url)
        if self._enabled:
            log.info("Discord alerts enabled")
        else:
            log.info("Discord alerts disabled (no webhook configured)")

    def _send(self, payload: dict):
        if not self._enabled:
            return
        def _post():
            try:
                r = requests.post(self._url, json=payload, timeout=8)
                if r.status_code not in (200, 204):
                    log.warning("Discord alert failed: HTTP %s", r.status_code)
            except Exception as exc:
                log.warning("Discord alert error: %s", exc)
        threading.Thread(target=_post, daemon=True).start()

    def _embed(self, title: str, description: str, color: int, fields: list) -> dict:
        return {
            "embeds": [{
                "title":       title,
                "description": description,
                "color":       color,
                "fields":      fields,
                "footer":      {"text": "Aurentis AI Trading System"},
                "timestamp":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }]
        }

    def trade_opened(self, coin: str, side: str, size_usd: float,
                     entry: float, sl: float, tp: float,
                     reasons: list, strength: float):
        color  = 0x00C851 if side == "long" else 0xFF4444
        emoji  = "🟢" if side == "long" else "🔴"
        self._send(self._embed(
            title=f"{emoji} {side.upper()} {coin} Opened",
            description=f"New paper trade opened on **{coin}**",
            color=color,
            fields=[
                {"name": "Side",     "value": side.upper(),           "inline": True},
                {"name": "Size",     "value": f"${size_usd:,.0f}",    "inline": True},
                {"name": "Entry",    "value": f"{entry:.5g}",         "inline": True},
                {"name": "Stop Loss","value": f"{sl:.5g}",            "inline": True},
                {"name": "Take Profit","value": f"{tp:.5g}",          "inline": True},
                {"name": "Strength", "value": f"{strength:.2f}",      "inline": True},
                {"name": "Signals",  "value": ", ".join(reasons[:4]), "inline": False},
            ],
        ))

    def trade_closed(self, coin: str, side: str, pnl: float, pnl_pct: float,
                     reason: str, duration_min: float):
        won   = pnl >= 0
        color = 0x00C851 if won else 0xFF4444
        emoji = "✅" if won else "❌"
        self._send(self._embed(
            title=f"{emoji} {coin} Closed — {'WIN' if won else 'LOSS'}",
            description=f"Paper trade closed: **{coin}** {side.upper()}",
            color=color,
            fields=[
                {"name": "P&L",      "value": f"${pnl:+,.2f}",              "inline": True},
                {"name": "P&L %",    "value": f"{pnl_pct*100:+.2f}%",       "inline": True},
                {"name": "Reason",   "value": reason,                        "inline": True},
                {"name": "Duration", "value": f"{duration_min:.0f} min",     "inline": True},
            ],
        ))

    def circuit_breaker(self, reason: str, halt_hours: float):
        self._send(self._embed(
            title="⚠️ Circuit Breaker Triggered",
            description=f"Trading halted for **{halt_hours:.0f}h**",
            color=0xFF9900,
            fields=[{"name": "Reason", "value": reason, "inline": False}],
        ))

    def daily_summary(self, portfolio_value: float, day_pnl: float,
                      trades: int, win_rate: float):
        won   = day_pnl >= 0
        color = 0x00C851 if won else 0xFF4444
        self._send(self._embed(
            title="📊 Daily Summary",
            description="End-of-day performance report",
            color=color,
            fields=[
                {"name": "Portfolio Value", "value": f"${portfolio_value:,.2f}", "inline": True},
                {"name": "Day P&L",         "value": f"${day_pnl:+,.2f}",        "inline": True},
                {"name": "Trades Today",    "value": str(trades),                 "inline": True},
                {"name": "Win Rate",        "value": f"{win_rate:.1f}%",          "inline": True},
            ],
        ))

"""
Aurentis AI — Discord webhook + Twilio SMS alerts.
Discord: rich embeds on trade open, close, circuit breaker, daily summary.
SMS:     concise text to phone number when a trade opens or closes.
"""
import logging
import threading
import time
from typing import Optional

import requests

from src import config as cfg

log = logging.getLogger("aurentis.alerts")


class DiscordAlerter:
    def __init__(self, webhook_url: str, enabled: bool = True):
        self._url       = webhook_url
        self._enabled   = enabled and bool(webhook_url)
        self._sms_ok    = all([cfg.TWILIO_SID, cfg.TWILIO_TOKEN,
                               cfg.TWILIO_FROM, cfg.SMS_TO])

        if self._enabled:
            log.info("Discord alerts enabled")
        else:
            log.info("Discord alerts disabled (no webhook configured)")

        if self._sms_ok:
            log.info("SMS alerts enabled → %s", cfg.SMS_TO[-4:].rjust(10, '*'))
        else:
            log.info("SMS alerts disabled (set TWILIO_* + SMS_TO_NUMBER to enable)")

    # ── SMS ───────────────────────────────────────────────────────────────────
    def send_sms(self, message: str) -> None:
        """Send a text message via Twilio (fire-and-forget in background thread)."""
        if not self._sms_ok:
            return
        def _post():
            try:
                from twilio.rest import Client
                client = Client(cfg.TWILIO_SID, cfg.TWILIO_TOKEN)
                client.messages.create(
                    body  = message[:1600],   # Twilio 1600-char limit
                    from_ = cfg.TWILIO_FROM,
                    to    = cfg.SMS_TO,
                )
                log.info("SMS sent to *%s", cfg.SMS_TO[-4:])
            except Exception as exc:
                log.warning("SMS failed: %s", exc)
        threading.Thread(target=_post, daemon=True, name="sms").start()

    # ── Discord helpers ───────────────────────────────────────────────────────
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

    # ── Trade alerts ──────────────────────────────────────────────────────────
    def trade_opened(self, coin: str, side: str, size_usd: float,
                     entry: float, sl: float, tp: float,
                     reasons: list, strength: float):
        color  = 0x00C851 if side == "long" else 0xFF4444
        emoji  = "🟢" if side == "long" else "🔴"
        arrow  = "▲ BUY" if side == "long" else "▼ SELL"

        # Discord
        self._send(self._embed(
            title=f"{emoji} {side.upper()} {coin} Opened",
            description=f"New paper trade opened on **{coin}**",
            color=color,
            fields=[
                {"name": "Side",       "value": side.upper(),           "inline": True},
                {"name": "Size",       "value": f"${size_usd:,.0f}",    "inline": True},
                {"name": "Entry",      "value": f"{entry:.5g}",         "inline": True},
                {"name": "Stop Loss",  "value": f"{sl:.5g}",            "inline": True},
                {"name": "Take Profit","value": f"{tp:.5g}",            "inline": True},
                {"name": "Strength",   "value": f"{strength:.2f}",      "inline": True},
                {"name": "Signals",    "value": ", ".join(reasons[:4]), "inline": False},
            ],
        ))

        # SMS
        self.send_sms(
            f"Aurentis AI {arrow} {coin}\n"
            f"Entry: {entry:.5g} | Size: ${size_usd:,.0f}\n"
            f"Stop: {sl:.5g} | Target: {tp:.5g}\n"
            f"Signals: {', '.join(reasons[:3])}"
        )

    def trade_closed(self, coin: str, side: str, pnl: float, pnl_pct: float,
                     reason: str, duration_min: float):
        won   = pnl >= 0
        color = 0x00C851 if won else 0xFF4444
        emoji = "✅" if won else "❌"
        result = "WIN" if won else "LOSS"

        # Discord
        self._send(self._embed(
            title=f"{emoji} {coin} Closed — {result}",
            description=f"Paper trade closed: **{coin}** {side.upper()}",
            color=color,
            fields=[
                {"name": "P&L",      "value": f"${pnl:+,.2f}",              "inline": True},
                {"name": "P&L %",    "value": f"{pnl_pct*100:+.2f}%",       "inline": True},
                {"name": "Reason",   "value": reason,                        "inline": True},
                {"name": "Duration", "value": f"{duration_min:.0f} min",     "inline": True},
            ],
        ))

        # SMS
        dur_str = f"{duration_min:.0f}m" if duration_min < 60 else f"{duration_min/60:.1f}h"
        self.send_sms(
            f"Aurentis AI {emoji} CLOSED {coin} — {result}\n"
            f"P&L: ${pnl:+,.2f} ({pnl_pct*100:+.2f}%)\n"
            f"Reason: {reason} | Held: {dur_str}"
        )

    def circuit_breaker(self, reason: str, halt_hours: float):
        self._send(self._embed(
            title="⚠️ Circuit Breaker Triggered",
            description=f"Trading halted for **{halt_hours:.0f}h**",
            color=0xFF9900,
            fields=[{"name": "Reason", "value": reason, "inline": False}],
        ))
        self.send_sms(f"⚠️ Aurentis AI HALTED\nReason: {reason}\nDuration: {halt_hours:.0f}h")

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
        self.send_sms(
            f"📊 Aurentis AI Daily\n"
            f"Value: ${portfolio_value:,.2f} | P&L: ${day_pnl:+,.2f}\n"
            f"Trades: {trades} | Win Rate: {win_rate:.1f}%"
        )

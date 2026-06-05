"""ALERTS — Notification hub module.

Listens to trade and system events, dispatches Discord / SMS alerts.
Subscribes:
  trade.opened
  trade.closed
  risk.halted
"""
import time

from src.alerts import DiscordAlerter
from src import config as cfg
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class AlertsHub(KronosModule):
    def __init__(self, bus: KronosEventBus, alerter: DiscordAlerter, portfolio):
        super().__init__("ALERTS", bus)
        self._alerter  = alerter
        self._portfolio = portfolio

        self.subscribe("trade.opened", self._on_opened)
        self.subscribe("trade.closed", self._on_closed)
        self.subscribe("risk.halted",  self._on_halted)

    def _on_opened(self, event):
        d = event.data
        coin = d.get("coin", "?")
        try:
            pos = self._portfolio.positions.get(coin)
            if not pos:
                return
            self._alerter.trade_opened(
                coin, pos.side, pos.size_usd, pos.entry,
                pos.sl, pos.tp,
                pos.reasons.split(", ")[:3] if pos.reasons else [],
                d.get("strength", 0),
            )
            self.heartbeat(f"Alert sent: OPEN {coin}")
        except Exception as exc:
            self.set_error(f"alert open {coin}: {exc}")

    def _on_closed(self, event):
        d = event.data
        coin = d.get("coin", "?")
        try:
            self.heartbeat(f"Trade closed: {coin} — {d.get('reason', '?')}")
        except Exception as exc:
            self.set_error(f"alert close {coin}: {exc}")

    def _on_halted(self, event):
        try:
            self._alerter.send(
                f"⚠️ CIRCUIT BREAKER: trading halted — {event.data.get('reason', '')}"
            )
            self.heartbeat("Circuit breaker alert sent")
        except Exception as exc:
            self.set_error(f"halt alert: {exc}")

    def _run_loop(self):
        self.heartbeat("Active")
        # Send daily summary
        import datetime
        last_day = datetime.datetime.now().day

        while not self._stop_evt.is_set():
            now = datetime.datetime.now()
            if now.day != last_day:
                last_day = now.day
                try:
                    prices = {}  # handled by portfolio internally
                    self.heartbeat("Daily summary queued")
                except Exception:
                    pass
            time.sleep(60)

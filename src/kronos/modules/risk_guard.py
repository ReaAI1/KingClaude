"""RISK — Risk guard module.

Validates signals against circuit breakers and position limits before
approving them for execution.
Subscribes:
  signal.generated
  prices.update    (to run portfolio exit checks)
Publishes:
  signal.approved   same payload as signal.generated
  signal.rejected   {coin, reason, signal: ...}
  risk.halted       {reason, until}
  risk.resumed      {}
"""
import time
from typing import Optional

from src import config as cfg
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class RiskGuard(KronosModule):
    def __init__(self, bus: KronosEventBus, portfolio):
        super().__init__("RISK", bus)
        self._portfolio = portfolio
        self._last_halt_announce: float = 0.0

        self.subscribe("signal.generated", self._on_signal)
        self.subscribe("prices.update",    self._on_prices)

    # ── Event handlers (called in publisher's thread — must be fast) ──────────

    def _on_prices(self, event):
        """Run portfolio exit checks on every price tick."""
        try:
            self._portfolio.check_exits(event.data)
        except Exception as exc:
            self.set_error(f"exit check: {exc}")

    def _on_signal(self, event):
        sig = event.data
        coin = sig["coin"]

        # Circuit breaker
        if self._portfolio.halted and time.time() < self._portfolio.halt_until:
            remaining = (self._portfolio.halt_until - time.time()) / 3600
            if time.time() - self._last_halt_announce > 300:
                self.heartbeat(f"HALTED — {remaining:.1f}h remaining")
                self._last_halt_announce = time.time()
            self.publish("signal.rejected", {"coin": coin, "reason": "halted", "signal": sig})
            return

        if self._portfolio.halted:
            self._portfolio.halted = False
            self.publish("risk.resumed", {})

        # Already in position
        if coin in self._portfolio.positions:
            self._handle_flip(coin, sig)
            return

        # Max positions
        if len(self._portfolio.positions) >= cfg.MAX_POSITIONS:
            self.publish("signal.rejected", {
                "coin": coin, "reason": "max_positions", "signal": sig
            })
            return

        # Threshold
        if sig["direction"] not in ("buy", "sell"):
            return
        if sig["strength"] < cfg.SIGNAL_THRESHOLD:
            return

        self.publish("signal.approved", sig)
        self.heartbeat(
            f"APPROVED {sig['direction'].upper()} {coin} str={sig['strength']:.2f}"
        )

    def _handle_flip(self, coin: str, sig: dict):
        pos = self._portfolio.positions.get(coin)
        if not pos:
            return
        flip = (
            (sig["direction"] == "buy"  and pos.side == "short" and sig["strength"] > 0.55) or
            (sig["direction"] == "sell" and pos.side == "long"  and sig["strength"] > 0.55)
        )
        if flip:
            self.publish("exit.requested", {
                "coin": coin, "reason": "signal_flip", "fraction": 1.0
            })

    # ── This module is event-driven; _run_loop just keeps it alive ────────────

    def _run_loop(self):
        self.heartbeat("Active")
        while not self._stop_evt.is_set():
            # Periodic self-check
            p = self._portfolio
            n = len(p.positions)
            halted = "HALTED" if (p.halted and time.time() < p.halt_until) else "ok"
            self.heartbeat(f"Positions {n}/{cfg.MAX_POSITIONS}  [{halted}]")
            time.sleep(30)

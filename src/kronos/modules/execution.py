"""EXECUTION — Trade execution module.

Opens and closes positions through the Portfolio engine.
Subscribes:
  signal.approved   → open position
  exit.requested    → close position
Publishes:
  trade.opened   position dict
  trade.closed   trade record dict
"""
import time

from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class Execution(KronosModule):
    def __init__(self, bus: KronosEventBus, portfolio, shared_state):
        super().__init__("EXECUTION", bus)
        self._portfolio = portfolio
        self._state = shared_state  # for reading live prices

        self.subscribe("signal.approved", self._on_approved)
        self.subscribe("exit.requested",  self._on_exit)

    def _on_approved(self, event):
        sig = event.data
        coin = sig["coin"]
        direction = sig["direction"]

        prices = self._state.prices
        if not prices:
            return

        # Reconstruct a minimal signal-like object
        class _Sig:
            pass
        s = _Sig()
        s.strength  = sig["strength"]
        s.reasons   = sig.get("reasons", [])
        s.components = sig.get("components", {})

        try:
            ok = self._portfolio.open(coin, direction, s, prices)
            if ok:
                pos = self._portfolio.positions.get(coin)
                if pos:
                    rec = pos.to_dict(prices.get(coin, pos.entry))
                    self.publish("trade.opened", rec)
                    self.heartbeat(
                        f"OPEN {direction.upper()} {coin} "
                        f"${pos.size_usd:,.0f} @ {pos.entry:.4g}"
                    )
                    # Update dashboard status
                    arrow = ">>>" if direction == "buy" else "<<<"
                    self._state.set_status(
                        f"{arrow} {direction.upper()} {coin}  str={sig['strength']:.2f}"
                    )
        except Exception as exc:
            self.set_error(f"open {coin}: {exc}")

    def _on_exit(self, event):
        d = event.data
        coin     = d["coin"]
        reason   = d.get("reason", "manual")
        fraction = d.get("fraction", 1.0)
        prices   = self._state.prices
        try:
            self._portfolio.close(coin, reason, prices, fraction)
            rec = {"coin": coin, "reason": reason, "fraction": fraction}
            self.publish("trade.closed", rec)
            self.heartbeat(f"CLOSE {coin} reason={reason}")
        except Exception as exc:
            self.set_error(f"close {coin}: {exc}")

    def _run_loop(self):
        self.heartbeat("Active")
        while not self._stop_evt.is_set():
            n = len(self._portfolio.positions)
            val = self._portfolio.value(self._state.prices) if self._state.prices else 0
            self.heartbeat(f"{n} open  value=${val:,.0f}")
            time.sleep(15)

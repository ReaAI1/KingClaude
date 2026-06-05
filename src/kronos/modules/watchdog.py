"""WATCHDOG — System health monitor and snapshot module.

Detects stale prices, monitors all module heartbeats, saves equity snapshots.
Publishes:
  health.report   {modules: [...], stale: bool}
"""
import ctypes
import sys
import time
from typing import Dict, List

from src import config as cfg
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class Watchdog(KronosModule):
    HEALTH_INTERVAL   = 60    # seconds
    SNAPSHOT_INTERVAL = 600   # 10 min equity snapshot

    def __init__(self, bus: KronosEventBus, portfolio, shared_state, db):
        super().__init__("WATCHDOG", bus)
        self._portfolio   = portfolio
        self._state       = shared_state
        self._db          = db
        self._last_btc    = 0.0
        self._stale_count = 0
        self._last_snap   = 0.0

    def _run_loop(self):
        self.heartbeat("Active")

        # Windows keep-awake
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            except Exception:
                pass

        while not self._stop_evt.is_set():
            try:
                self._check_prices()
                self._check_snapshots()

                # Windows keep-awake refresh
                if sys.platform == "win32":
                    try:
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
                    except Exception:
                        pass

                self.heartbeat(
                    f"stale={self._stale_count}  "
                    f"BTC=${self._state.prices.get('BTC', 0):,.0f}"
                )
            except Exception as exc:
                self.set_error(str(exc))

            time.sleep(self.HEALTH_INTERVAL)

    def _check_prices(self):
        cur_btc = self._state.prices.get("BTC", 0)
        if cur_btc == self._last_btc and cur_btc > 0:
            self._stale_count += 1
            self.log.warning("Prices stale (%dx)", self._stale_count)
            # Force DATA module refresh via event
            self.publish("data.force_refresh", {})
        else:
            self._stale_count = 0
        self._last_btc = self._state.prices.get("BTC", 0)

    def _check_snapshots(self):
        if time.time() - self._last_snap > self.SNAPSHOT_INTERVAL:
            if self._state.prices:
                try:
                    self._portfolio.snapshot(self._state.prices)
                    self._last_snap = time.time()
                except Exception as exc:
                    self.set_error(f"snapshot: {exc}")

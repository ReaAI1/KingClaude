"""SCANNER — Technical signal generation module.

Runs every LOOP_SECS, scores each coin with multi-indicator confluence.
Publishes:
  signal.generated   Signal.to_dict() with extra 'coin' key
"""
import time
from typing import Dict

from src import config as cfg
from src.signals import generate_signal
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class Scanner(KronosModule):
    def __init__(self, bus: KronosEventBus, brain):
        super().__init__("SCANNER", bus)
        self._brain = brain
        self._candles: Dict[str, list] = {}
        self._htf: Dict[str, list]     = {}
        self._prices: Dict[str, float] = {}
        self._lock = __import__("threading").Lock()

        self.subscribe("candles.update", self._on_candles)
        self.subscribe("htf.update",     self._on_htf)
        self.subscribe("prices.update",  self._on_prices)

    def _on_candles(self, event):
        with self._lock:
            self._candles[event.data["coin"]] = event.data["bars"]

    def _on_htf(self, event):
        with self._lock:
            self._htf[event.data["coin"]] = event.data["bars"]

    def _on_prices(self, event):
        with self._lock:
            self._prices.update(event.data)

    def _run_loop(self):
        self.heartbeat("Waiting for data...")
        # Wait until we have data
        for _ in range(120):
            if self._stop_evt.is_set():
                return
            with self._lock:
                ready = len(self._candles) >= len(cfg.TRADING_PAIRS)
            if ready:
                break
            time.sleep(2)

        while not self._stop_evt.is_set():
            summaries = []
            for coin in cfg.TRADING_PAIRS:
                if self._stop_evt.is_set():
                    break
                with self._lock:
                    candles = list(self._candles.get(coin, []))
                    htf     = list(self._htf.get(coin, []))
                if len(candles) < 50:
                    continue
                try:
                    sig = generate_signal(
                        coin, candles, htf, self._brain.ml, cfg.SIGNAL_THRESHOLD
                    )
                    self.publish("signal.generated", sig.to_dict())
                    d = sig.direction[0].upper()
                    summaries.append(f"{coin}:{d}{sig.strength:.2f}")
                except Exception as exc:
                    self.set_error(f"{coin}: {exc}")

            if summaries:
                self.heartbeat("  ".join(summaries[:5]))

            time.sleep(cfg.LOOP_SECS)

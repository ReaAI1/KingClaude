"""BRAIN — Machine learning engine module.

Trains per-coin LightGBM classifiers.  Listens for candle updates and
retrains on schedule.
Publishes:
  model.trained   {coin: str, accuracy: float}
"""
import time
from typing import Dict, List

from src import config as cfg
from src.ml_engine import MLEngine
from src.kronos.base import KronosModule
from src.kronos.bus import KronosEventBus


class Brain(KronosModule):
    RETRAIN_CHECK_INTERVAL = 600  # check every 10 min

    def __init__(self, bus: KronosEventBus):
        super().__init__("BRAIN", bus)
        self.ml = MLEngine(
            min_rows     = cfg.ML_MIN_ROWS,
            label_bars   = cfg.ML_LABEL_BARS,
            label_thresh = cfg.ML_LABEL_THRESH,
        )
        self._candles: Dict[str, list] = {}
        self._lock_candles = __import__("threading").Lock()

        self.subscribe("candles.update", self._on_candles)

    def _on_candles(self, event):
        d = event.data
        with self._lock_candles:
            self._candles[d["coin"]] = d["bars"]

    def _run_loop(self):
        # Wait for initial candle data before first train
        self.heartbeat("Waiting for candles...")
        for _ in range(60):
            if self._stop_evt.is_set():
                return
            with self._lock_candles:
                if len(self._candles) >= len(cfg.TRADING_PAIRS):
                    break
            time.sleep(2)

        self._train_all()

        while not self._stop_evt.is_set():
            time.sleep(self.RETRAIN_CHECK_INTERVAL)
            retrain_secs = cfg.ML_RETRAIN_HOURS * 3600
            for coin in cfg.TRADING_PAIRS:
                if self._stop_evt.is_set():
                    break
                if self.ml.needs_retrain(coin, retrain_secs):
                    self._train_coin(coin)

    def _train_all(self):
        for coin in cfg.TRADING_PAIRS:
            if self._stop_evt.is_set():
                return
            self._train_coin(coin)
            time.sleep(1.0)

    def _train_coin(self, coin: str):
        with self._lock_candles:
            candles = list(self._candles.get(coin, []))
        if len(candles) < cfg.ML_MIN_ROWS:
            return
        try:
            self.ml.train(coin, candles)
            acc = self.ml.accuracy(coin)
            self.heartbeat(f"{coin} trained acc={acc*100:.1f}%")
            self.publish("model.trained", {"coin": coin, "accuracy": acc})
        except Exception as exc:
            self.set_error(f"train {coin}: {exc}")

    def predict(self, coin: str, candles: list):
        return self.ml.predict(coin, candles)

    def summary(self) -> dict:
        return self.ml.summary()

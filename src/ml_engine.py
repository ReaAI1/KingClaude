"""
Aurentis AI — LightGBM / RandomForest ML signal engine.
Trains per-coin binary classifiers on OHLCV-derived features.
Falls back to RandomForest if lightgbm is not installed.
"""
import logging
import threading
import time
import warnings
from typing import Dict, Optional, Tuple

import numpy as np

warnings.filterwarnings("ignore")
warnings.filterwarnings("ignore", message=".*feature names.*")
log = logging.getLogger("aurentis.ml")


class MLEngine:
    """
    Per-coin ML classifier.
    Thread-safe — train() and predict() can be called from different threads.
    """

    def __init__(self, min_rows: int = 80, label_bars: int = 3, label_thresh: float = 0.003):
        self.min_rows     = min_rows
        self.label_bars   = label_bars
        self.label_thresh = label_thresh

        self._models:     Dict[str, object] = {}
        self._accuracy:   Dict[str, float]  = {}
        self._last_train: Dict[str, float]  = {}
        self._lock        = threading.Lock()

    # ── Classifier factory ────────────────────────────────────────────────────
    @staticmethod
    def _make_clf():
        try:
            import lightgbm as lgb
            return lgb.LGBMClassifier(
                n_estimators=80, learning_rate=0.08,
                max_depth=4, num_leaves=15,
                min_child_samples=20, subsample=0.8,
                colsample_bytree=0.8, random_state=42,
                verbose=-1, n_jobs=1,   # single-threaded — safe on free-tier
            )
        except ImportError:
            from sklearn.ensemble import RandomForestClassifier
            return RandomForestClassifier(
                n_estimators=50, max_depth=4,
                random_state=42, n_jobs=1,
            )

    # ── Train ─────────────────────────────────────────────────────────────────
    def train(self, coin: str, candles: list) -> None:
        from src.indicators import build_feature_matrix

        X, y = build_feature_matrix(candles, self.label_bars, self.label_thresh)
        if len(X) < self.min_rows:
            log.debug("ML skip %s — only %d rows", coin, len(X))
            return

        mask = y != 0
        Xb   = X[mask]
        yb   = np.where(y[mask] == 1, 1, 0)

        if len(np.unique(yb)) < 2 or len(Xb) < 40:
            log.debug("ML skip %s — insufficient class balance", coin)
            return

        # Simple holdout instead of cross-val — much less memory
        split  = int(len(Xb) * 0.80)
        X_tr, X_val = Xb[:split], Xb[split:]
        y_tr, y_val = yb[:split], yb[split:]

        clf = self._make_clf()
        try:
            clf.fit(X_tr, y_tr)
            acc = float((clf.predict(X_val) == y_val).mean()) if len(X_val) else 0.5
            with self._lock:
                self._models[coin]      = clf
                self._accuracy[coin]    = acc
                self._last_train[coin]  = time.time()
            log.info("ML trained %-6s  acc=%.1f%%  rows=%d", coin, acc * 100, len(Xb))
        except Exception as exc:
            log.warning("ML train %s failed: %s", coin, exc)

    # ── Predict ───────────────────────────────────────────────────────────────
    def predict(self, coin: str, candles: list) -> Tuple[float, float]:
        """
        Returns (prob_up, prob_down).
        Both are in [0, 1].  Returns (0.5, 0.5) when no model is ready.
        """
        with self._lock:
            clf = self._models.get(coin)
        if clf is None:
            return 0.5, 0.5

        from src.indicators import build_feature_matrix
        X, _ = build_feature_matrix(candles, self.label_bars, self.label_thresh)
        if len(X) == 0:
            return 0.5, 0.5

        try:
            proba = clf.predict_proba(X[-1:].copy())[0]
            # classes_ = [0=down, 1=up]
            if len(proba) == 2:
                return float(proba[1]), float(proba[0])
        except Exception:
            pass
        return 0.5, 0.5

    # ── Helpers ───────────────────────────────────────────────────────────────
    def needs_retrain(self, coin: str, retrain_every_secs: float = 14_400) -> bool:
        return time.time() - self._last_train.get(coin, 0) > retrain_every_secs

    def accuracy(self, coin: str) -> float:
        return self._accuracy.get(coin, 0.0)

    def is_trained(self, coin: str) -> bool:
        return coin in self._models

    def summary(self) -> dict:
        with self._lock:
            return {
                coin: {"accuracy": self._accuracy.get(coin, 0.0),
                       "trained": coin in self._models}
                for coin in set(list(self._models) + list(self._accuracy))
            }

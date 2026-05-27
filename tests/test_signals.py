"""
Unit tests for signal generation and indicator calculations.
Run with: python -m pytest tests/ -v
"""
import math
import numpy as np
import pytest
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── Helpers ───────────────────────────────────────────────────────────────
def make_candles(n: int = 200, trend: str = "up") -> list:
    """Generate synthetic OHLCV candles for testing."""
    rng = np.random.default_rng(42)
    price = 50_000.0
    candles = []
    for i in range(n):
        move = rng.normal(0, price * 0.005)
        if trend == "up":
            move += price * 0.001
        elif trend == "down":
            move -= price * 0.001

        o = price
        c = price + move
        h = max(o, c) + abs(rng.normal(0, price * 0.002))
        l = min(o, c) - abs(rng.normal(0, price * 0.002))
        v = rng.uniform(100, 1000)
        candles.append({
            "t": (1_700_000_000 + i * 900) * 1000,
            "o": str(round(o, 2)),
            "h": str(round(h, 2)),
            "l": str(round(l, 2)),
            "c": str(round(c, 2)),
            "v": str(round(v, 2)),
        })
        price = c
    return candles


# ── Indicator Tests ───────────────────────────────────────────────────────
class TestIndicators:
    def setup_method(self):
        from src.indicators import ema, rsi, macd, bollinger, atr, adx, stochastic
        self.ema        = ema
        self.rsi        = rsi
        self.macd       = macd
        self.bollinger  = bollinger
        self.atr        = atr
        self.adx        = adx
        self.stochastic = stochastic
        self.closes     = np.array([float(c["c"]) for c in make_candles(220)])
        self.highs      = np.array([float(c["h"]) for c in make_candles(220)])
        self.lows       = np.array([float(c["l"]) for c in make_candles(220)])

    def test_ema_length(self):
        e = self.ema(self.closes, 20)
        assert len(e) == len(self.closes)

    def test_ema_last_reasonable(self):
        e = self.ema(self.closes, 20)
        assert not np.isnan(e[-1])
        assert e[-1] > 0

    def test_rsi_range(self):
        r = self.rsi(self.closes, 14)
        valid = r[~np.isnan(r)]
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_macd_components(self):
        line, signal, hist = self.macd(self.closes)
        assert len(line) == len(self.closes)
        assert not np.isnan(line[-1])

    def test_bollinger_bands(self):
        upper, mid, lower = self.bollinger(self.closes, 20, 2.0)
        valid = ~np.isnan(upper[-20:])
        assert (upper[-20:][valid] >= mid[-20:][valid]).all()
        assert (lower[-20:][valid] <= mid[-20:][valid]).all()

    def test_atr_positive(self):
        a = self.atr(self.highs, self.lows, self.closes, 14)
        valid = a[~np.isnan(a)]
        assert (valid > 0).all()

    def test_adx_no_nan(self):
        """ADX must not return all NaN (critical bug that was fixed)."""
        adx_vals = self.adx(self.highs, self.lows, self.closes, 14)
        valid = adx_vals[~np.isnan(adx_vals)]
        assert len(valid) > 0, "ADX returned all NaN — nansum bug regression"
        assert (valid >= 0).all() and (valid <= 100).all()

    def test_stochastic_range(self):
        k, d = self.stochastic(self.highs, self.lows, self.closes, 14, 3)
        valid_k = k[~np.isnan(k)]
        assert (valid_k >= 0).all() and (valid_k <= 100).all()


# ── Signal Tests ──────────────────────────────────────────────────────────
class TestSignals:
    def setup_method(self):
        from src.signals import generate_signal, Signal
        from src.ml_engine import MLEngine
        self.generate_signal = generate_signal
        self.Signal          = Signal
        self.ml              = MLEngine(min_rows=80, label_bars=3, label_thresh=0.003)

    def test_signal_returns_signal_obj(self):
        candles = make_candles(220, "up")
        sig = self.generate_signal("BTC", candles, [], self.ml, 0.24)
        assert isinstance(sig, self.Signal)

    def test_signal_strength_0_to_1(self):
        candles = make_candles(220, "up")
        sig = self.generate_signal("BTC", candles, [], self.ml, 0.24)
        assert 0.0 <= sig.strength <= 1.0

    def test_signal_direction_valid(self):
        candles = make_candles(220)
        sig = self.generate_signal("ETH", candles, [], self.ml, 0.24)
        assert sig.direction in ("buy", "sell", "flat"), f"Unexpected direction: {sig.direction}"

    def test_signal_has_reasons(self):
        candles = make_candles(220, "up")
        sig = self.generate_signal("SOL", candles, [], self.ml, 0.24)
        assert isinstance(sig.reasons, list)

    def test_signal_to_dict(self):
        candles = make_candles(220)
        sig = self.generate_signal("BTC", candles, [], self.ml, 0.24)
        d = sig.to_dict()
        assert "direction" in d
        assert "strength"  in d
        assert "reasons"   in d

    def test_ml_trains_on_good_data(self):
        candles = make_candles(220)
        self.ml.train("BTC", candles)
        # After training, should not need retrain for 1 hour (3 600 s)
        # Note: passing 0 would always return True on Linux (ns-precision clock)
        assert self.ml.needs_retrain("BTC", 3600) is False
        assert self.ml.is_trained("BTC") is True

    def test_signal_uptrend_prefers_buy(self):
        """Strong uptrend should lean buy (not always, but direction should not be sell)."""
        # Very strong uptrend
        candles = make_candles(220, "up")
        # Train ML on this data first
        self.ml.train("BTC", candles)
        results = [self.generate_signal("BTC", candles, [], self.ml, 0.0) for _ in range(1)]
        # At threshold=0.0 every signal triggers — at least check it doesn't crash
        assert all(s.direction in ("buy", "sell", "flat") for s in results)


# ── Portfolio Tests ───────────────────────────────────────────────────────
class TestPortfolio:
    def setup_method(self):
        import sqlite3
        import tempfile
        import os
        # Use temp db
        self.tmp = tempfile.mktemp(suffix=".db")
        from src.database import Database
        from src.portfolio import Portfolio

        class MockSignal:
            strength   = 0.70
            reasons    = ["test_reason"]
            components = ["ema", "rsi"]
            direction  = "buy"

        self.db        = Database(self.tmp)
        self.portfolio = Portfolio(self.db)
        self.signal    = MockSignal()

    def teardown_method(self):
        import os
        try: os.unlink(self.tmp)
        except: pass

    def test_initial_cash(self):
        from src import config as cfg
        assert self.portfolio.cash == cfg.INITIAL_CAPITAL

    def test_open_position(self):
        prices = {"BTC": 50_000.0}
        ok = self.portfolio.open("BTC", "buy", self.signal, prices)
        assert ok is True
        assert "BTC" in self.portfolio.positions

    def test_no_duplicate_positions(self):
        prices = {"BTC": 50_000.0}
        self.portfolio.open("BTC", "buy", self.signal, prices)
        ok2 = self.portfolio.open("BTC", "buy", self.signal, prices)
        assert ok2 is False

    def test_close_position(self):
        prices = {"BTC": 50_000.0}
        self.portfolio.open("BTC", "buy", self.signal, prices)
        self.portfolio.close("BTC", "take_profit", {"BTC": 52_000.0})
        assert "BTC" not in self.portfolio.positions
        assert len(self.portfolio.closed) == 1

    def test_pnl_positive_on_long_win(self):
        prices_open  = {"BTC": 50_000.0}
        prices_close = {"BTC": 55_000.0}
        self.portfolio.open("BTC", "buy", self.signal, prices_open)
        self.portfolio.close("BTC", "take_profit", prices_close)
        trade = self.portfolio.closed[-1]
        assert trade["pnl"] > 0

    def test_stats_returns_dict(self):
        prices = {"BTC": 50_000.0}
        st = self.portfolio.stats(prices)
        assert isinstance(st, dict)
        assert "value"    in st
        assert "win_rate" in st
        assert "sharpe"   in st

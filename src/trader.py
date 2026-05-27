"""
Aurentis AI — Core trading engine.
Runs in a background thread. Feeds live data to web dashboard via shared state.
"""
import ctypes
import logging
import sys
import threading
import time
from typing import Dict, List

from src import config as cfg
from src.api import get_prices, get_candles
from src.ml_engine import MLEngine
from src.signals import generate_signal, Signal
from src.portfolio import Portfolio
from src.alerts import DiscordAlerter

log = logging.getLogger("aurentis.trader")


class SharedState:
    """Thread-safe container read by the web dashboard."""
    def __init__(self):
        self._lock     = threading.Lock()
        self.prices:   Dict[str, float] = {}
        self.signals:  Dict[str, dict]  = {}
        self.candles:  Dict[str, list]  = {}   # coin -> 15m candles
        self.chart_candles: list        = []   # BTC 1h for chart
        self.status:   str              = "Starting..."
        self.uptime:   float            = 0.0
        self.loop_count: int            = 0

    def update_prices(self, p: dict):
        with self._lock:
            self.prices.update(p)

    def update_signal(self, coin: str, sig: Signal):
        with self._lock:
            self.signals[coin] = sig.to_dict()

    def update_candles(self, coin: str, c: list):
        with self._lock:
            self.candles[coin] = c

    def update_chart(self, c: list):
        with self._lock:
            self.chart_candles = c

    def set_status(self, s: str):
        with self._lock:
            self.status = s

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "prices":        dict(self.prices),
                "signals":       dict(self.signals),
                "chart_candles": list(self.chart_candles),
                "status":        self.status,
                "uptime":        round(self.uptime, 0),
                "loop_count":    self.loop_count,
            }


class TradingEngine:
    def __init__(self, db, alerter: DiscordAlerter):
        self.db       = db
        self.alerter  = alerter
        self.portfolio = Portfolio(db)
        self.ml        = MLEngine(
            min_rows    = cfg.ML_MIN_ROWS,
            label_bars  = cfg.ML_LABEL_BARS,
            label_thresh= cfg.ML_LABEL_THRESH,
        )
        self.state     = SharedState()
        self._stop_evt = threading.Event()
        self._start_ts = time.time()

    # ── Bootstrap ─────────────────────────────────────────────────────────────
    def bootstrap(self):
        log.info("Bootstrapping — fetching candles & training ML...")
        self._load_candles()
        self._train_ml_all()
        log.info("Bootstrap complete.")

    def _load_candles(self):
        for coin in cfg.TRADING_PAIRS:
            c = get_candles(cfg.HL_REST_URL, coin, cfg.PRIMARY_TF, cfg.CANDLE_LOOKBACK)
            if c:
                self.state.update_candles(coin, c)
                log.info("Candles %-6s %s×%s  (%d bars)", coin, len(c), cfg.PRIMARY_TF, len(c))
            h = get_candles(cfg.HL_REST_URL, coin, cfg.HTF_TF, cfg.HTF_LOOKBACK)
            if h:
                with self.state._lock:
                    if not hasattr(self.state, "htf_candles"):
                        self.state.htf_candles = {}
                    self.state.htf_candles[coin] = h
            time.sleep(0.4)
        chart = get_candles(cfg.HL_REST_URL, cfg.CHART_COIN, cfg.CHART_TF, cfg.CHART_BARS)
        if chart:
            self.state.update_chart(chart)

    def _train_ml_all(self):
        for coin in cfg.TRADING_PAIRS:
            with self.state._lock:
                candles = self.state.candles.get(coin, [])
            if len(candles) >= cfg.ML_MIN_ROWS:
                self.ml.train(coin, candles)

    # ── Background threads (all wrapped in outer retry loops) ─────────────────
    def _price_thread(self):
        """Fetch live prices every 5 s. Never stops — outer loop restarts on crash."""
        while not self._stop_evt.is_set():
            try:
                p = get_prices(cfg.HL_REST_URL)
                if p:
                    self.state.update_prices(p)
                    self.portfolio.check_exits(p)
                time.sleep(5)
            except Exception as exc:
                log.warning("price_thread error (retrying in 10 s): %s", exc)
                time.sleep(10)

    def _candle_thread(self):
        """Refresh OHLCV data. Full reload every 15 min, chart every 5 min."""
        last_full  = time.time()
        last_chart = time.time()
        while not self._stop_evt.is_set():
            try:
                time.sleep(60)
                now = time.time()
                if now - last_full > 900:
                    self._load_candles()
                    last_full = now
                elif now - last_chart > 300:
                    chart = get_candles(cfg.HL_REST_URL, cfg.CHART_COIN,
                                        cfg.CHART_TF, cfg.CHART_BARS)
                    if chart:
                        self.state.update_chart(chart)
                    last_chart = now
            except Exception as exc:
                log.warning("candle_thread error (retrying in 30 s): %s", exc)
                time.sleep(30)

    def _ml_thread(self):
        """Retrain ML models every 4 hours when needed."""
        while not self._stop_evt.is_set():
            try:
                time.sleep(600)
                for coin in cfg.TRADING_PAIRS:
                    if self._stop_evt.is_set():
                        break
                    retrain_secs = cfg.ML_RETRAIN_HOURS * 3600
                    if self.ml.needs_retrain(coin, retrain_secs):
                        with self.state._lock:
                            candles = self.state.candles.get(coin, [])
                        if candles:
                            self.ml.train(coin, candles)
            except Exception as exc:
                log.warning("ml_thread error (retrying in 60 s): %s", exc)
                time.sleep(60)

    def _watchdog_thread(self):
        """Detect stale prices, keep Windows awake, auto-recover."""
        last_btc       = 0.0
        stale_count    = 0
        while not self._stop_evt.is_set():
            try:
                time.sleep(120)
                cur = self.state.prices.get("BTC", 0)
                if cur == last_btc and cur > 0:
                    stale_count += 1
                    log.warning("Prices stale (%dx) — force refresh", stale_count)
                    p = get_prices(cfg.HL_REST_URL)
                    if p:
                        self.state.update_prices(p)
                        stale_count = 0
                else:
                    stale_count = 0
                last_btc = self.state.prices.get("BTC", 0)
                # Windows keep-awake (prevent sleep/hibernate)
                if sys.platform == "win32":
                    try:
                        ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
                    except Exception:
                        pass
            except Exception as exc:
                log.warning("watchdog error (retrying in 30 s): %s", exc)
                time.sleep(30)

    def _snapshot_thread(self):
        """Save equity snapshots every 10 minutes."""
        while not self._stop_evt.is_set():
            try:
                time.sleep(600)
                if self.state.prices:
                    self.portfolio.snapshot(self.state.prices)
            except Exception as exc:
                log.warning("snapshot_thread error: %s", exc)
                time.sleep(30)

    # ── Main trading loop ─────────────────────────────────────────────────────
    def _trading_loop(self):
        import datetime
        last_day  = datetime.datetime.now().day
        last_week = datetime.datetime.now().isocalendar()[1]
        _consecutive_errors = 0

        while not self._stop_evt.is_set():
            try:
                self.state.uptime     = time.time() - self._start_ts
                self.state.loop_count += 1
                _consecutive_errors   = 0

                # Daily / weekly resets
                now = datetime.datetime.now()
                if now.day != last_day:
                    last_day = now.day
                    self.portfolio.daily_reset(self.state.prices)
                    try:
                        self.alerter.daily_summary(
                            self.portfolio.value(self.state.prices),
                            self.portfolio.stats(self.state.prices).get("day_pct", 0),
                            self.portfolio.stats(self.state.prices).get("trades", 0),
                            self.portfolio.stats(self.state.prices).get("win_rate", 0),
                        )
                    except Exception:
                        pass
                if now.isocalendar()[1] != last_week:
                    last_week = now.isocalendar()[1]
                    self.portfolio.weekly_reset(self.state.prices)

                # Wait until we have price data
                if not self.state.prices:
                    time.sleep(5)
                    continue

                # Evaluate signals for each coin
                for coin in cfg.TRADING_PAIRS:
                    if self._stop_evt.is_set():
                        break
                    try:
                        with self.state._lock:
                            candles = self.state.candles.get(coin, [])
                            htf     = getattr(self.state, "htf_candles", {}).get(coin, [])

                        if len(candles) < 50:
                            continue

                        sig = generate_signal(
                            coin, candles, htf, self.ml, cfg.SIGNAL_THRESHOLD
                        )
                        self.state.update_signal(coin, sig)

                        # Signal-flip exit
                        if coin in self.portfolio.positions:
                            pos = self.portfolio.positions[coin]
                            if sig.direction == "buy" and pos.side == "short" and sig.strength > 0.55:
                                self.portfolio.close(coin, "signal_flip", self.state.prices)
                                try:
                                    self.alerter.trade_closed(coin, pos.side, 0, 0, "signal_flip",
                                                              (time.time() - pos.opened) / 60)
                                except Exception:
                                    pass
                            elif sig.direction == "sell" and pos.side == "long" and sig.strength > 0.55:
                                self.portfolio.close(coin, "signal_flip", self.state.prices)
                                try:
                                    self.alerter.trade_closed(coin, pos.side, 0, 0, "signal_flip",
                                                              (time.time() - pos.opened) / 60)
                                except Exception:
                                    pass
                            continue

                        # Open new position
                        if (sig.direction in ("buy", "sell")
                                and sig.strength >= cfg.SIGNAL_THRESHOLD
                                and not (self.portfolio.halted and time.time() < self.portfolio.halt_until)):
                            ok = self.portfolio.open(coin, sig.direction, sig, self.state.prices)
                            if ok:
                                pos = self.portfolio.positions[coin]
                                try:
                                    self.alerter.trade_opened(
                                        coin, pos.side, pos.size_usd, pos.entry,
                                        pos.sl, pos.tp, sig.reasons, sig.strength
                                    )
                                except Exception:
                                    pass
                                arrow = ">>>" if sig.direction == "buy" else "<<<"
                                self.state.set_status(
                                    f"{arrow} {sig.direction.upper()} {coin} "
                                    f"str={sig.strength:.2f}"
                                )
                    except Exception as coin_exc:
                        log.warning("trading_loop coin %s error: %s", coin, coin_exc)

                # Update scan status
                with self.state._lock:
                    n_pos = len(self.portfolio.positions)
                    val   = self.portfolio.value(self.state.prices)
                self.state.set_status(
                    f"Scanning {len(cfg.TRADING_PAIRS)} pairs | "
                    f"Positions {n_pos}/{cfg.MAX_POSITIONS} | "
                    f"Value ${val:,.2f}"
                )

            except Exception as exc:
                _consecutive_errors += 1
                wait = min(30 * _consecutive_errors, 300)
                log.error("trading_loop crash #%d (retry in %ds): %s",
                          _consecutive_errors, wait, exc)
                time.sleep(wait)
                continue

            time.sleep(cfg.LOOP_SECS)

    # ── Start / Stop ──────────────────────────────────────────────────────────
    def start(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            except Exception:
                pass

        threads = [
            threading.Thread(target=self._price_thread,   daemon=True, name="prices"),
            threading.Thread(target=self._candle_thread,  daemon=True, name="candles"),
            threading.Thread(target=self._ml_thread,      daemon=True, name="ml"),
            threading.Thread(target=self._watchdog_thread,daemon=True, name="watchdog"),
            threading.Thread(target=self._snapshot_thread,daemon=True, name="snapshots"),
            threading.Thread(target=self._trading_loop,   daemon=True, name="trading"),
        ]
        for t in threads:
            t.start()
        log.info("All engine threads started.")

    def stop(self):
        self._stop_evt.set()
        if sys.platform == "win32":
            try:
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except Exception:
                pass

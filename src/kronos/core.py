"""
KRONOS — Central trading system orchestrator.

Replaces TradingEngine. Creates and wires all modules through the event bus,
maintains SharedState for backward-compatible web dashboard endpoints, and
exposes a module registry for the new /api/kronos endpoint.

Module graph (data flow):
  DATA → [prices.update, candles.update, htf.update, chart.update]
       ↓
  BRAIN (candles.update) → model.trained
       ↓
  SCANNER (candles + htf + prices) → signal.generated
       ↓
  RISK (signal.generated) → signal.approved / exit.requested
       ↓
  EXECUTION (signal.approved / exit.requested) → trade.opened / trade.closed
       ↓
  ALERTS (trade.opened / trade.closed)
  WATCHDOG (periodic health + snapshots)
"""

import datetime
import logging
import sys
import threading
import time
from typing import Dict, List, Optional

from src import config as cfg
from src.alerts import DiscordAlerter
from src.database import Database
from src.portfolio import Portfolio

from src.kronos.bus import KronosEventBus
from src.kronos.modules.data_feed import DataFeed
from src.kronos.modules.brain import Brain
from src.kronos.modules.scanner import Scanner
from src.kronos.modules.risk_guard import RiskGuard
from src.kronos.modules.execution import Execution
from src.kronos.modules.watchdog import Watchdog
from src.kronos.modules.alerts_hub import AlertsHub

log = logging.getLogger("kronos.core")


# ── SharedState (backward-compatible with existing web server) ────────────────

class SharedState:
    """Thread-safe container read by the web dashboard."""

    def __init__(self):
        self._lock          = threading.Lock()
        self.prices:        Dict[str, float] = {}
        self.signals:       Dict[str, dict]  = {}
        self.candles:       Dict[str, list]  = {}
        self.htf_candles:   Dict[str, list]  = {}
        self.chart_candles: list             = []
        self.status:        str              = "Starting..."
        self.uptime:        float            = 0.0
        self.loop_count:    int              = 0
        self._start_ts:     float            = time.time()

    def update_prices(self, p: dict):
        with self._lock:
            self.prices.update(p)
            self.uptime = time.time() - self._start_ts

    def update_signal(self, coin: str, sig: dict):
        with self._lock:
            self.signals[coin] = sig

    def update_candles(self, coin: str, c: list):
        with self._lock:
            self.candles[coin] = c

    def update_htf(self, coin: str, c: list):
        with self._lock:
            self.htf_candles[coin] = c

    def update_chart(self, c: list):
        with self._lock:
            self.chart_candles = c

    def set_status(self, s: str):
        with self._lock:
            self.status = s
            self.loop_count += 1

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


# ── KRONOS Orchestrator ───────────────────────────────────────────────────────

class Kronos:
    """
    The central orchestrator.  Wire all modules through the event bus
    then call bootstrap() + start().
    """

    # Node positions for the web graph (polar coords: angle in degrees, radius 0-1)
    # KRONOS sits at center; modules orbit around it
    MODULE_POSITIONS = {
        "DATA":      {"angle":   0, "r": 1.0, "label": "[01] DATA"},
        "BRAIN":     {"angle":  45, "r": 1.0, "label": "[02] BRAIN"},
        "SCANNER":   {"angle":  90, "r": 1.0, "label": "[03] SCANNER"},
        "RISK":      {"angle": 135, "r": 1.0, "label": "[04] RISK"},
        "EXECUTION": {"angle": 180, "r": 1.0, "label": "[05] EXECUTION"},
        "PORTFOLIO": {"angle": 225, "r": 1.0, "label": "[06] PORTFOLIO"},
        "WATCHDOG":  {"angle": 270, "r": 1.0, "label": "[07] WATCHDOG"},
        "ALERTS":    {"angle": 315, "r": 1.0, "label": "[08] ALERTS"},
    }

    def __init__(self, db: Database, alerter: DiscordAlerter):
        self.db       = db
        self.alerter  = alerter
        self.state    = SharedState()
        self.bus      = KronosEventBus()
        self.portfolio = Portfolio(db)

        # Create modules
        self.data_feed  = DataFeed(self.bus)
        self.brain      = Brain(self.bus)
        self.scanner    = Scanner(self.bus, self.brain)
        self.risk       = RiskGuard(self.bus, self.portfolio)
        self.execution  = Execution(self.bus, self.portfolio, self.state)
        self.watchdog   = Watchdog(self.bus, self.portfolio, self.state, db)
        self.alerts     = AlertsHub(self.bus, alerter, self.portfolio)

        self._modules: List = [
            self.data_feed, self.brain, self.scanner, self.risk,
            self.execution, self.watchdog, self.alerts,
        ]

        # Register "PORTFOLIO" as a virtual observable node (not a thread)
        self._portfolio_node = _PortfolioNode(self.portfolio, self.state)

        # Wire state updates from bus events
        self._wire_state_updates()

        self._stop_evt = threading.Event()
        self._start_ts = time.time()

    # ── Event wiring ──────────────────────────────────────────────────────────

    def _wire_state_updates(self):
        """Keep SharedState in sync from bus events (for web dashboard)."""

        def on_prices(event):
            self.state.update_prices(event.data)
            n = len(self.portfolio.positions)
            val = self.portfolio.value(event.data)
            self.state.set_status(
                f"Scanning {len(cfg.TRADING_PAIRS)} pairs | "
                f"Positions {n}/{cfg.MAX_POSITIONS} | "
                f"Value ${val:,.0f}"
            )

        def on_candles(event):
            self.state.update_candles(event.data["coin"], event.data["bars"])

        def on_htf(event):
            self.state.update_htf(event.data["coin"], event.data["bars"])

        def on_chart(event):
            self.state.update_chart(event.data["bars"])

        def on_signal(event):
            self.state.update_signal(event.data["coin"], event.data)

        self.bus.subscribe("prices.update",   on_prices)
        self.bus.subscribe("candles.update",  on_candles)
        self.bus.subscribe("htf.update",      on_htf)
        self.bus.subscribe("chart.update",    on_chart)
        self.bus.subscribe("signal.generated", on_signal)

    # ── Bootstrap ─────────────────────────────────────────────────────────────

    def bootstrap(self):
        """Pre-load candles and train ML before going live. Called in bg thread."""
        log.info("KRONOS bootstrap — loading candles & training BRAIN...")

        from src.api import get_candles
        for coin in cfg.TRADING_PAIRS:
            try:
                bars = get_candles(cfg.HL_REST_URL, coin, cfg.PRIMARY_TF, cfg.CANDLE_LOOKBACK)
                if bars:
                    self.state.update_candles(coin, bars)
                    self.brain._on_candles(type("E", (), {"data": {"coin": coin, "bars": bars}})())
                htf = get_candles(cfg.HL_REST_URL, coin, cfg.HTF_TF, cfg.HTF_LOOKBACK)
                if htf:
                    self.state.update_htf(coin, htf)
                    self.scanner._htf[coin] = htf
                time.sleep(0.4)
            except Exception as exc:
                log.warning("Bootstrap candles %s: %s", coin, exc)

        try:
            chart = get_candles(cfg.HL_REST_URL, cfg.CHART_COIN, cfg.CHART_TF, cfg.CHART_BARS)
            if chart:
                self.state.update_chart(chart)
        except Exception as exc:
            log.warning("Bootstrap chart: %s", exc)

        # Train ML synchronously during bootstrap
        self.brain._train_all()
        log.info("KRONOS bootstrap complete.")

    # ── Start / Stop ──────────────────────────────────────────────────────────

    def start(self):
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000003)
            except Exception:
                pass

        for module in self._modules:
            module.start()

        log.info("KRONOS online — %d modules active.", len(self._modules))

    def stop(self):
        self._stop_evt.set()
        for module in self._modules:
            module.stop()
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)
            except Exception:
                pass

    # ── Backward-compat accessors (used by existing web server) ──────────────

    @property
    def ml(self):
        return self.brain

    # ── KRONOS graph snapshot ─────────────────────────────────────────────────

    def kronos_snapshot(self) -> dict:
        """Full system state for the /api/kronos endpoint."""
        module_dicts = [m.to_dict() for m in self._modules]
        # Add PORTFOLIO virtual node
        module_dicts.append(self._portfolio_node.to_dict())

        prices  = self.state.prices
        stats   = self.portfolio.stats(prices) if prices else {}

        return {
            "modules":     module_dicts,
            "positions":   module_dicts,  # alias kept for old clients
            "bus": {
                "total_events": self.bus.total_events,
                "recent":       self.bus.recent(15),
            },
            "system": {
                "uptime_secs": round(time.time() - self._start_ts),
                "pairs":       len(cfg.TRADING_PAIRS),
                "mode":        cfg.EXECUTION_MODE,
                "value":       round(stats.get("value", 0), 2),
                "ret_pct":     round(stats.get("ret_pct", 0), 3),
                "trades":      stats.get("trades", 0),
                "win_rate":    stats.get("win_rate", 0),
            },
            "module_positions": self.MODULE_POSITIONS,
        }


# ── Virtual PORTFOLIO node ────────────────────────────────────────────────────

class _PortfolioNode:
    """Exposes Portfolio stats as a KronosModule-compatible dict."""

    def __init__(self, portfolio, state):
        self._portfolio = portfolio
        self._state = state
        self.name = "PORTFOLIO"

    def to_dict(self) -> dict:
        p = self._portfolio
        n = len(p.positions)
        prices = self._state.prices
        val = p.value(prices) if prices else 0
        return {
            "name":       "PORTFOLIO",
            "status":     "RUNNING",
            "health":     "warn" if p.halted else "ok",
            "last_event": f"{n} open  ${val:,.0f}",
            "errors":     0,
            "age_secs":   0,
        }

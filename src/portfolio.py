"""
Aurentis AI — Paper trading portfolio engine.
Simulates fills, fees, slippage, stops, and partial TPs.
State persists to SQLite and survives restarts (< 24 h old).
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src import config as cfg

log = logging.getLogger("aurentis.portfolio")


@dataclass
class Position:
    coin:          str
    side:          str        # 'long' | 'short'
    size_usd:      float
    contracts:     float
    entry:         float
    sl:            float
    tp:            float
    trail_best:    float
    reasons:       str
    opened:        float      # Unix timestamp
    partial_done:  bool = False
    components:    str  = ""  # comma-joined component names

    def pnl(self, price: float) -> float:
        if self.side == "long":
            return (price - self.entry) * self.contracts
        return (self.entry - price) * self.contracts

    def pnl_pct(self, price: float) -> float:
        return self.pnl(price) / (self.size_usd + 1e-10)

    def age_str(self) -> str:
        m = (time.time() - self.opened) / 60
        return f"{m:.0f}m" if m < 60 else f"{m/60:.1f}h"

    def to_dict(self, price: float = 0.0) -> dict:
        p = price or self.entry
        return {
            "coin":         self.coin,
            "side":         self.side,
            "size_usd":     round(self.size_usd, 2),
            "entry":        self.entry,
            "current":      p,
            "pnl":          round(self.pnl(p), 2),
            "pnl_pct":      round(self.pnl_pct(p) * 100, 2),
            "sl":           self.sl,
            "tp":           self.tp,
            "reasons":      self.reasons,
            "age":          self.age_str(),
            "partial_done": self.partial_done,
        }


class Portfolio:
    def __init__(self, db):
        self.cash       = cfg.INITIAL_CAPITAL
        self.initial    = cfg.INITIAL_CAPITAL
        self.positions: Dict[str, Position] = {}
        self.closed:    List[dict]           = []
        self.realized   = 0.0
        self.fees       = 0.0
        self.day_start  = cfg.INITIAL_CAPITAL
        self.week_start = cfg.INITIAL_CAPITAL
        self.peak_value = cfg.INITIAL_CAPITAL
        self.halted     = False
        self.halt_until = 0.0
        self._lock      = threading.Lock()
        self._db        = db
        self._restore()

    # ── Persist ───────────────────────────────────────────────────────────────
    def _save(self):
        state = {
            "cash":       self.cash,
            "realized":   self.realized,
            "fees":       self.fees,
            "initial":    self.initial,
            "day_start":  self.day_start,
            "week_start": self.week_start,
            "peak_value": self.peak_value,
            "ts":         time.time(),
        }
        positions = [p.__dict__ for p in self.positions.values()]
        self._db.set("portfolio_state",    json.dumps(state))
        self._db.set("portfolio_positions", json.dumps(positions))

    def _restore(self):
        raw = self._db.get("portfolio_state")
        if not raw:
            return
        s = json.loads(raw)
        if time.time() - s.get("ts", 0) > 86_400:
            return
        self.cash       = s["cash"]
        self.realized   = s["realized"]
        self.fees       = s["fees"]
        self.initial    = s["initial"]
        self.day_start  = s.get("day_start",  cfg.INITIAL_CAPITAL)
        self.week_start = s.get("week_start", cfg.INITIAL_CAPITAL)
        self.peak_value = s.get("peak_value", cfg.INITIAL_CAPITAL)
        raw_pos = self._db.get("portfolio_positions")
        if raw_pos:
            for p in json.loads(raw_pos):
                p.setdefault("partial_done", False)
                p.setdefault("components",   "")
                self.positions[p["coin"]] = Position(**p)
        # restore recent trade history for dashboard display
        trades = self._db.recent_trades(50)
        self.closed = trades
        log.info(
            "Portfolio restored — cash=$%.2f positions=%s trades_loaded=%d",
            self.cash, list(self.positions), len(self.closed),
        )

    # ── Value ─────────────────────────────────────────────────────────────────
    def value(self, prices: dict) -> float:
        pos_val = sum(
            p.size_usd + p.pnl(prices.get(p.coin, p.entry))
            for p in self.positions.values()
        )
        return self.cash + pos_val

    # ── Open ──────────────────────────────────────────────────────────────────
    def open(self, coin: str, direction: str, signal, prices: dict) -> bool:
        with self._lock:
            if self.halted and time.time() < self.halt_until:
                return False
            if coin in self.positions:
                return False
            if len(self.positions) >= cfg.MAX_POSITIONS:
                return False

            price = prices.get(coin, 0)
            if price <= 0:
                return False

            val      = self.value(prices)
            size_pct = cfg.POSITION_SIZE_PCT * (0.7 + 0.6 * signal.strength)
            size_usd = min(val * size_pct, self.cash * 0.92)
            if size_usd < 20:
                return False

            slip = price * (cfg.SLIPPAGE_BPS / 10_000)
            fee  = size_usd * cfg.TAKER_FEE

            if direction == "buy":
                fill = price + slip
                sl   = fill * (1 - cfg.STOP_LOSS_PCT)
                tp   = fill * (1 + cfg.TAKE_PROFIT_PCT)
                side = "long"
            else:
                fill = price - slip
                sl   = fill * (1 + cfg.STOP_LOSS_PCT)
                tp   = fill * (1 - cfg.TAKE_PROFIT_PCT)
                side = "short"

            self.cash -= size_usd + fee
            self.fees += fee
            self.positions[coin] = Position(
                coin=coin, side=side, size_usd=size_usd,
                contracts=size_usd / fill, entry=fill,
                sl=sl, tp=tp, trail_best=fill,
                reasons=", ".join(signal.reasons),
                opened=time.time(),
                partial_done=False,
                components=",".join(
                    getattr(signal, "components", [])
                    if isinstance(getattr(signal, "components", []), list)
                    else []
                ),
            )
            self._save()
            log.info(
                "OPEN %s %s $%.0f @ %.5g  SL=%.5g TP=%.5g  str=%.2f [%s]",
                side.upper(), coin, size_usd, fill, sl, tp,
                signal.strength, ", ".join(signal.reasons[:3]),
            )
            return True

    # ── Close ─────────────────────────────────────────────────────────────────
    def close(self, coin: str, reason: str, prices: dict, fraction: float = 1.0):
        with self._lock:
            pos = self.positions.get(coin)
            if not pos:
                return

            price = prices.get(coin, pos.entry)
            slip  = price * (cfg.SLIPPAGE_BPS / 10_000)
            fill  = (price - slip) if pos.side == "long" else (price + slip)

            close_usd = pos.size_usd * fraction
            fee       = close_usd * cfg.TAKER_FEE
            if pos.side == "long":
                gross = (fill - pos.entry) * (close_usd / pos.entry)
            else:
                gross = (pos.entry - fill) * (close_usd / pos.entry)
            net = gross - fee

            self.cash     += close_usd + net
            self.realized += net
            self.fees     += fee
            dur = (time.time() - pos.opened) / 60

            if fraction < 1.0:
                pos.size_usd  *= (1 - fraction)
                pos.contracts *= (1 - fraction)
                pos.partial_done = True
                if pos.side == "long":
                    pos.sl = max(pos.sl, pos.entry * 1.001)
                else:
                    pos.sl = min(pos.sl, pos.entry * 0.999)
                self._save()
                log.info("PARTIAL %s %s %.0f%% net=%+.2f reason=%s",
                         pos.side.upper(), coin, fraction * 100, net, reason)
                return

            rec = {
                "coin":         coin,
                "side":         pos.side,
                "size":         pos.size_usd,
                "entry":        pos.entry,
                "exit":         fill,
                "pnl":          round(net, 2),
                "pnl_pct":      round(net / pos.size_usd, 4),
                "reason":       reason,
                "duration_min": round(dur, 1),
            }
            self.closed.append(rec)
            if len(self.closed) > 200:
                self.closed = self.closed[-200:]

            self._db.insert_trade(coin, pos.side, pos.size_usd, pos.entry,
                                  fill, net, fee, net / pos.size_usd, reason, dur)

            # Notify adaptive weights
            from src.signals import adaptive_weights
            comps = [c for c in pos.components.split(",") if c]
            adaptive_weights().record(comps, net >= 0)

            del self.positions[coin]
            self._save()
            tag = "WIN " if net >= 0 else "LOSS"
            log.info("%s %s %s entry=%.5g exit=%.5g pnl=%+.2f (%.1f%%) reason=%s dur=%.0fm",
                     tag, pos.side.upper(), coin, pos.entry, fill,
                     net, net / pos.size_usd * 100, reason, dur)

    # ── Check exits every price tick ─────────────────────────────────────────
    def check_exits(self, prices: dict):
        to_partial = []
        to_close   = []

        with self._lock:
            for coin, pos in list(self.positions.items()):
                price = prices.get(coin)
                if not price:
                    continue
                pnl_p = pos.pnl_pct(price)

                # Partial TP
                if not pos.partial_done and pnl_p >= cfg.PARTIAL_TP_PCT:
                    to_partial.append(coin)

                # Trailing stop
                if pos.side == "long":
                    if price > pos.trail_best:
                        pos.trail_best = price
                        new_sl = price * (1 - cfg.TRAILING_STOP_PCT)
                        if new_sl > pos.sl:
                            pos.sl = new_sl
                    if price <= pos.sl:
                        to_close.append((coin, "stop_loss"))
                    elif price >= pos.tp:
                        to_close.append((coin, "take_profit"))
                else:
                    if price < pos.trail_best:
                        pos.trail_best = price
                        new_sl = price * (1 + cfg.TRAILING_STOP_PCT)
                        if new_sl < pos.sl:
                            pos.sl = new_sl
                    if price >= pos.sl:
                        to_close.append((coin, "stop_loss"))
                    elif price <= pos.tp:
                        to_close.append((coin, "take_profit"))

                # 48h time exit
                if time.time() - pos.opened > 172_800:
                    to_close.append((coin, "time_exit_48h"))

            # Circuit breakers
            val = self.value(prices)
            self.peak_value = max(self.peak_value, val)

            daily_dd  = (val - self.day_start)  / self.day_start  * 100  if self.day_start  else 0
            weekly_dd = (val - self.week_start) / self.week_start * 100  if self.week_start else 0
            all_dd    = (val - self.peak_value) / self.peak_value * 100  if self.peak_value else 0

            if daily_dd <= -cfg.MAX_DAILY_LOSS_PCT and not self.halted:
                self.halted     = True
                self.halt_until = time.time() + 4 * 3600
                log.warning("CIRCUIT BREAKER: daily loss %.1f%% — pausing 4h", -daily_dd)
            if weekly_dd <= -cfg.MAX_WEEKLY_LOSS_PCT and not self.halted:
                self.halted     = True
                self.halt_until = time.time() + 24 * 3600
                log.warning("CIRCUIT BREAKER: weekly loss %.1f%% — pausing 24h", -weekly_dd)
            if all_dd <= -cfg.MAX_DRAWDOWN_PCT and not self.halted:
                self.halted     = True
                self.halt_until = time.time() + 7 * 24 * 3600
                log.warning("CIRCUIT BREAKER: drawdown %.1f%% — pausing 7d", -all_dd)

        for coin in to_partial:
            self.close(coin, "partial_tp", prices, fraction=0.50)
        for coin, reason in to_close:
            self.close(coin, reason, prices, fraction=1.0)

    # ── Daily / weekly reset ──────────────────────────────────────────────────
    def daily_reset(self, prices: dict):
        val = self.value(prices)
        self.day_start = val
        if not self.halted:
            pass
        elif time.time() >= self.halt_until:
            self.halted = False
        log.info("Daily reset — day_start=$%.2f", val)

    def weekly_reset(self, prices: dict):
        self.week_start = self.value(prices)
        log.info("Weekly reset — week_start=$%.2f", self.week_start)

    # ── Snapshot ──────────────────────────────────────────────────────────────
    def snapshot(self, prices: dict):
        val = self.value(prices)
        self.peak_value = max(self.peak_value, val)
        self._db.insert_snapshot(val, self.cash, self.realized)

    # ── Stats ─────────────────────────────────────────────────────────────────
    def stats(self, prices: dict) -> dict:
        import math
        val    = self.value(prices)
        closed = self.closed
        wins   = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]
        total  = len(closed)
        pf     = 0.0
        if losses:
            gw  = sum(t["pnl"] for t in wins)
            gl  = abs(sum(t["pnl"] for t in losses))
            pf  = gw / (gl + 1e-9)

        # Sharpe from recent snapshots
        rows = self._db.recent_snapshots(30)
        sharpe = 0.0
        if len(rows) > 5:
            vals  = [r["value"] for r in rows]
            rets  = np.diff(vals) / (np.array(vals[:-1]) + 1e-9)
            if float(np.std(rets)) > 0:
                sharpe = float(np.mean(rets)) / float(np.std(rets)) * math.sqrt(144)

        return {
            "value":       round(val, 2),
            "initial":     round(self.initial, 2),
            "cash":        round(self.cash, 2),
            "realized":    round(self.realized, 2),
            "fees":        round(self.fees, 2),
            "ret_pct":     round((val - self.initial) / self.initial * 100, 3),
            "day_pct":     round((val - self.day_start) / self.day_start * 100, 3) if self.day_start else 0,
            "trades":      total,
            "win_rate":    round(len(wins) / total * 100, 1) if total else 0,
            "profit_factor": round(pf, 2),
            "avg_win":     round(sum(t["pnl"] for t in wins)   / len(wins),   2) if wins   else 0,
            "avg_loss":    round(sum(t["pnl"] for t in losses)  / len(losses), 2) if losses else 0,
            "sharpe":      round(sharpe, 2),
            "open_count":  len(self.positions),
            "halted":      self.halted,
            "halt_until":  self.halt_until,
        }

    def open_positions_list(self, prices: dict) -> list:
        return [pos.to_dict(prices.get(pos.coin, pos.entry))
                for pos in self.positions.values()]

    def recent_trades_list(self, n: int = 20) -> list:
        return list(reversed(self.closed[-n:]))


import numpy as np

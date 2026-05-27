"""
Aurentis AI — Multi-indicator signal engine with adaptive weights.
Combines EMA, RSI, MACD, Bollinger, Stochastic, Supertrend, ADX, Volume,
HTF bias, and ML probability into a single directional score.
"""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from src import indicators as ind

log = logging.getLogger("aurentis.signals")


# ── Signal dataclass ──────────────────────────────────────────────────────────

@dataclass
class Signal:
    coin:       str
    direction:  str          # 'buy' | 'sell' | 'flat'
    strength:   float        # 0-1 composite score
    reasons:    List[str]    = field(default_factory=list)
    ml_prob:    float        = 0.5
    adx_val:    float        = 0.0
    rsi_val:    float        = 50.0
    components: dict         = field(default_factory=dict)   # per-indicator votes (+1/−1/0)
    ml_up:      float        = 0.5
    ml_dn:      float        = 0.5

    def to_dict(self) -> dict:
        return {
            "coin":       self.coin,
            "direction":  self.direction,
            "strength":   round(self.strength, 3),
            "reasons":    self.reasons,
            "ml_prob":    round(self.ml_prob, 3),
            "ml_up":      round(self.ml_up, 3),
            "ml_dn":      round(self.ml_dn, 3),
            "adx":        round(self.adx_val, 1),
            "rsi":        round(self.rsi_val, 1),
            "components": self.components,
        }


# ── Adaptive weights ──────────────────────────────────────────────────────────

class AdaptiveWeights:
    """
    Tracks per-component win/loss history and slowly adjusts weights
    so that consistently correct indicators get more influence.
    """
    COMPONENTS = ["ema", "rsi", "macd", "bb", "stoch", "supertrend",
                  "volume", "adx", "ml", "htf"]
    DECAY      = 0.97
    FLOOR      = 0.30
    CAP        = 3.00

    def __init__(self):
        self._w = {c: 1.0 for c in self.COMPONENTS}
        self._history: deque = deque(maxlen=500)

    def get(self, comp: str) -> float:
        return self._w.get(comp, 1.0)

    def record(self, components: List[str], won: bool) -> None:
        score = 1.0 if won else -0.5
        for comp in components:
            if comp in self._w:
                self._w[comp] = self._w[comp] * self.DECAY + score * (1 - self.DECAY)
                self._w[comp] = max(self.FLOOR, min(self.CAP, self._w[comp]))
        self._history.append({"comps": components, "won": won})

    def to_dict(self) -> dict:
        return {k: round(v, 3) for k, v in self._w.items()}


# Singleton — shared across the process
_AW = AdaptiveWeights()


def adaptive_weights() -> AdaptiveWeights:
    return _AW


# ── HTF bias helper ────────────────────────────────────────────────────────────

def _htf_bias(htf_candles: list) -> float:
    """Return +1 (bull), -1 (bear), 0 (neutral) from 1-hour candles."""
    if len(htf_candles) < 30:
        return 0.0
    c  = np.array([x["c"] for x in htf_candles], dtype=float)
    e9  = ind.ema(c, 9)
    e21 = ind.ema(c, 21)
    if np.isnan(e9[-1]) or np.isnan(e21[-1]):
        return 0.0
    rsi_v   = float(ind.rsi(c, 14)[-1])
    ema_bull = e9[-1] > e21[-1]
    if ema_bull and rsi_v < 70:
        return 1.0
    if not ema_bull and rsi_v > 30:
        return -1.0
    return 0.0


# ── Main signal function ──────────────────────────────────────────────────────

def generate_signal(
    coin:     str,
    candles:  list,
    htf:      list,
    ml_engine,          # MLEngine instance
    threshold: float,
) -> Signal:
    """
    Compute a composite buy/sell/hold signal for *coin*.
    Returns a Signal with strength in [0, 1].
    """
    if len(candles) < 50:
        return Signal(coin, "flat", 0.0, ["insufficient data"])

    c = np.array([x["c"] for x in candles], dtype=float)
    h = np.array([x["h"] for x in candles], dtype=float)
    l = np.array([x["l"] for x in candles], dtype=float)
    v = np.array([x["v"] for x in candles], dtype=float)

    buy_pts = sell_pts = max_pts = 0.0
    comps_b: List[str] = []
    comps_s: List[str] = []
    reasons: List[str] = []
    comp_votes: dict   = {}     # for dashboard component breakdown

    # ── EMA 9/21 ─────────────────────────────────────────────────────────────
    e9, e21 = ind.ema(c, 9), ind.ema(c, 21)
    w = _AW.get("ema")
    if not np.isnan(e9[-1]):
        max_pts += 2.5 * w
        diff, prev = e9[-1] - e21[-1], e9[-2] - e21[-2]
        if diff > 0 and prev <= 0:
            buy_pts += 2.5 * w; comps_b.append("ema"); reasons.append("EMA cross^"); comp_votes["ema"] = 1
        elif diff < 0 and prev >= 0:
            sell_pts += 2.5 * w; comps_s.append("ema"); reasons.append("EMA cross_"); comp_votes["ema"] = -1
        elif diff > 0:
            buy_pts  += 1.6 * w; comps_b.append("ema"); reasons.append("EMA bull"); comp_votes["ema"] = 1
        else:
            sell_pts += 1.6 * w; comps_s.append("ema"); reasons.append("EMA bear"); comp_votes["ema"] = -1

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi_a = ind.rsi(c, 14)
    rv    = float(rsi_a[-1])
    w     = _AW.get("rsi")
    max_pts += 2.5 * w
    if rv < 28:
        buy_pts  += 2.5 * w; comps_b.append("rsi"); reasons.append(f"RSI OS {rv:.0f}"); comp_votes["rsi"] = 1
    elif rv < 38:
        buy_pts  += 1.5 * w; comps_b.append("rsi"); reasons.append(f"RSI low {rv:.0f}"); comp_votes["rsi"] = 1
    elif rv > 72:
        sell_pts += 2.5 * w; comps_s.append("rsi"); reasons.append(f"RSI OB {rv:.0f}"); comp_votes["rsi"] = -1
    elif rv > 62:
        sell_pts += 1.5 * w; comps_s.append("rsi"); reasons.append(f"RSI hi {rv:.0f}"); comp_votes["rsi"] = -1
    else:
        comp_votes["rsi"] = 0

    # ── MACD ──────────────────────────────────────────────────────────────────
    ml_arr, sl_arr, hist_arr = ind.macd(c)
    w = _AW.get("macd")
    if not np.isnan(ml_arr[-1]):
        max_pts += 2.0 * w
        if ml_arr[-1] > sl_arr[-1] and ml_arr[-2] <= sl_arr[-2]:
            buy_pts  += 2.0 * w; comps_b.append("macd"); reasons.append("MACD bull"); comp_votes["macd"] = 1
        elif ml_arr[-1] < sl_arr[-1] and ml_arr[-2] >= sl_arr[-2]:
            sell_pts += 2.0 * w; comps_s.append("macd"); reasons.append("MACD bear"); comp_votes["macd"] = -1
        elif (hist_arr[-1] > 0 and not np.isnan(hist_arr[-2])
              and hist_arr[-1] > hist_arr[-2]):
            buy_pts  += 0.8 * w; comps_b.append("macd"); reasons.append("MACD mom+"); comp_votes["macd"] = 1
        elif (hist_arr[-1] < 0 and not np.isnan(hist_arr[-2])
              and hist_arr[-1] < hist_arr[-2]):
            sell_pts += 0.8 * w; comps_s.append("macd"); reasons.append("MACD mom-"); comp_votes["macd"] = -1
        else:
            comp_votes["macd"] = 0

    # ── Bollinger Bands ───────────────────────────────────────────────────────
    bb_up, bb_md, bb_dn = ind.bollinger(c, 20)
    w = _AW.get("bb")
    if not np.isnan(bb_up[-1]):
        max_pts += 2.0 * w
        rng    = bb_up[-1] - bb_dn[-1]
        bb_pos = (c[-1] - bb_dn[-1]) / (rng + 1e-10)
        if c[-1] < bb_dn[-1]:
            buy_pts  += 2.0 * w; comps_b.append("bb"); reasons.append("BB break low"); comp_votes["bb"] = 1
        elif c[-1] > bb_up[-1]:
            sell_pts += 2.0 * w; comps_s.append("bb"); reasons.append("BB break hi"); comp_votes["bb"] = -1
        elif bb_pos < 0.20:
            buy_pts  += 1.0 * w; comps_b.append("bb"); reasons.append("BB lo zone"); comp_votes["bb"] = 1
        elif bb_pos > 0.80:
            sell_pts += 1.0 * w; comps_s.append("bb"); reasons.append("BB hi zone"); comp_votes["bb"] = -1
        else:
            comp_votes["bb"] = 0

    # ── Stochastic (only extreme zones count) ─────────────────────────────────
    k_stoch, d_stoch = ind.stochastic(h, l, c, 14, 3)
    w  = _AW.get("stoch")
    kv = float(k_stoch[-1])
    dv = float(d_stoch[-1]) if not np.isnan(d_stoch[-1]) else 50.0
    if kv < 25:
        max_pts += 1.5 * w
        pts = 1.5 if kv > dv else 0.8
        buy_pts  += pts * w; comps_b.append("stoch")
        reasons.append(f"Stoch OS {kv:.0f}"); comp_votes["stoch"] = 1
    elif kv > 75:
        max_pts += 1.5 * w
        pts = 1.5 if kv < dv else 0.8
        sell_pts += pts * w; comps_s.append("stoch")
        reasons.append(f"Stoch OB {kv:.0f}"); comp_votes["stoch"] = -1
    else:
        comp_votes["stoch"] = 0

    # ── Supertrend ────────────────────────────────────────────────────────────
    st_trend, _ = ind.supertrend(h, l, c, 10, 3.0)
    w = _AW.get("supertrend")
    max_pts += 1.5 * w
    if st_trend[-1] == 1 and st_trend[-2] == -1:
        buy_pts  += 1.5 * w; comps_b.append("supertrend"); reasons.append("ST flip^"); comp_votes["supertrend"] = 1
    elif st_trend[-1] == -1 and st_trend[-2] == 1:
        sell_pts += 1.5 * w; comps_s.append("supertrend"); reasons.append("ST flip_"); comp_votes["supertrend"] = -1
    elif st_trend[-1] == 1:
        buy_pts  += 1.1 * w; comps_b.append("supertrend"); reasons.append("ST bull"); comp_votes["supertrend"] = 1
    else:
        sell_pts += 1.1 * w; comps_s.append("supertrend"); reasons.append("ST bear"); comp_votes["supertrend"] = -1

    # ── Volume spike ──────────────────────────────────────────────────────────
    avg_v   = float(np.mean(v[-20:-1])) if len(v) > 20 else float(v.mean())
    vr      = v[-1] / (avg_v + 1e-10)
    w       = _AW.get("volume")
    if vr > 1.8:
        if buy_pts > sell_pts:
            buy_pts  *= 1.0 + 0.20 * w; comps_b.append("volume")
            reasons.append(f"vol {vr:.1f}x"); comp_votes["volume"] = 1
        elif sell_pts > buy_pts:
            sell_pts *= 1.0 + 0.20 * w; comps_s.append("volume")
            reasons.append(f"vol {vr:.1f}x"); comp_votes["volume"] = -1
    else:
        comp_votes["volume"] = 0

    # ── ADX regime boost ──────────────────────────────────────────────────────
    adx_a = ind.adx(h, l, c, 14)
    adxv  = float(adx_a[-1]) if not np.isnan(adx_a[-1]) else 20.0
    w     = _AW.get("adx")
    if adxv > 25:
        boost = 1.0 + 0.12 * w * (adxv / 50)
        buy_pts  *= boost
        sell_pts *= boost
        reasons.append(f"ADX {adxv:.0f}T")

    # ── ATR quiet filter ──────────────────────────────────────────────────────
    atr_a   = ind.atr(h, l, c, 14)
    atr_pct = float(atr_a[-1]) / float(c[-1]) if c[-1] > 0 else 0
    if atr_pct < 0.002:
        buy_pts  *= 0.70
        sell_pts *= 0.70

    # ── ML signal (only adds to max_pts when non-neutral) ────────────────────
    prob_up, prob_dn = ml_engine.predict(coin, candles)
    w      = _AW.get("ml")
    ml_pts = 2.5 * w
    comp_votes["ml"] = 0
    if prob_up > 0.55 or prob_dn > 0.55:
        max_pts += ml_pts
        if prob_up > 0.62:
            contribution = ml_pts * (prob_up - 0.5) / 0.5
            buy_pts  += contribution; comps_b.append("ml")
            reasons.append(f"ML^{prob_up:.2f}"); comp_votes["ml"] = 1
        elif prob_dn > 0.62:
            contribution = ml_pts * (prob_dn - 0.5) / 0.5
            sell_pts += contribution; comps_s.append("ml")
            reasons.append(f"ML_{prob_dn:.2f}"); comp_votes["ml"] = -1

    # ── HTF bias (only adds to max_pts when non-neutral) ─────────────────────
    htf_bias = _htf_bias(htf)
    w        = _AW.get("htf")
    htf_pts  = 2.0 * w
    comp_votes["htf"] = int(htf_bias)
    if htf_bias != 0:
        max_pts += htf_pts
        if htf_bias > 0:
            buy_pts  += htf_pts * 0.8; comps_b.append("htf"); reasons.append("HTF bull")
        else:
            sell_pts += htf_pts * 0.8; comps_s.append("htf"); reasons.append("HTF bear")

    if max_pts == 0:
        return Signal(coin, "flat", 0.0, ["no data"], prob_up, adxv, rv, comp_votes, prob_up, prob_dn)

    buy_str  = min(buy_pts  / max_pts, 1.0)
    sell_str = min(sell_pts / max_pts, 1.0)

    if buy_str > sell_str and buy_str >= threshold:
        return Signal(coin, "buy",  buy_str,  reasons[:5], prob_up, adxv, rv, comp_votes, prob_up, prob_dn)
    if sell_str > buy_str and sell_str >= threshold:
        return Signal(coin, "sell", sell_str, reasons[:5], prob_dn, adxv, rv, comp_votes, prob_up, prob_dn)
    return Signal(coin, "flat", max(buy_str, sell_str), reasons[:3], prob_up, adxv, rv, comp_votes, prob_up, prob_dn)

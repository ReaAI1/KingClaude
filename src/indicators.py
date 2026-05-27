"""
Aurentis AI — Pure-numpy technical indicators.
No TA-Lib dependency. All functions accept numpy float arrays.
"""
import numpy as np
from typing import Tuple


def ema(a: np.ndarray, n: int) -> np.ndarray:
    e = np.full(len(a), np.nan)
    if len(a) < n:
        return e
    k = 2.0 / (n + 1)
    e[n - 1] = float(np.mean(a[:n]))
    for i in range(n, len(a)):
        e[i] = a[i] * k + e[i - 1] * (1 - k)
    return e


def sma(a: np.ndarray, n: int) -> np.ndarray:
    s = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        s[i] = float(np.mean(a[i - n + 1: i + 1]))
    return s


def rsi(a: np.ndarray, n: int = 14) -> np.ndarray:
    r = np.full(len(a), 50.0)
    if len(a) < n + 1:
        return r
    d  = np.diff(a.astype(float))
    g  = np.where(d > 0, d, 0.0)
    lo = np.where(d < 0, -d, 0.0)
    ag, al = float(np.mean(g[:n])), float(np.mean(lo[:n]))
    for i in range(n, len(d)):
        ag = (ag * (n - 1) + g[i])  / n
        al = (al * (n - 1) + lo[i]) / n
        r[i + 1] = 100.0 - 100.0 / (1 + ag / al) if al > 0 else 100.0
    return r


def macd(a: np.ndarray, fast=12, slow=26, signal=9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    ml = ema(a, fast) - ema(a, slow)
    sl = ema(np.where(np.isnan(ml), 0.0, ml), signal)
    return ml, sl, ml - sl


def bollinger(a: np.ndarray, n: int = 20, std: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    up = np.full(len(a), np.nan)
    md = np.full(len(a), np.nan)
    dn = np.full(len(a), np.nan)
    for i in range(n - 1, len(a)):
        sl = a[i - n + 1: i + 1]
        md[i] = float(np.mean(sl))
        sd     = float(np.std(sl, ddof=1))
        up[i]  = md[i] + std * sd
        dn[i]  = md[i] - std * sd
    return up, md, dn


def atr(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    prev_c = np.roll(c, 1); prev_c[0] = c[0]
    tr = np.maximum(h - l, np.maximum(np.abs(h - prev_c), np.abs(l - prev_c)))
    a  = np.full(len(c), np.nan)
    if len(c) < n:
        return a
    a[n - 1] = float(np.mean(tr[:n]))
    for i in range(n, len(c)):
        a[i] = (a[i - 1] * (n - 1) + tr[i]) / n
    return a


def adx(h: np.ndarray, l: np.ndarray, c: np.ndarray, n: int = 14) -> np.ndarray:
    result = np.full(len(c), np.nan)
    if len(c) < n * 2:
        return result
    atr_a  = atr(h, l, c, n)
    prev_h = np.roll(h, 1); prev_h[0] = h[0]
    prev_l = np.roll(l, 1); prev_l[0] = l[0]
    dm_pos = np.where((h - prev_h) > (prev_l - l), np.maximum(h - prev_h, 0.0), 0.0)
    dm_neg = np.where((prev_l - l) > (h - prev_h), np.maximum(prev_l - l, 0.0), 0.0)

    di_pos = np.full(len(c), np.nan)
    di_neg = np.full(len(c), np.nan)
    sp = float(np.nansum(dm_pos[1: n + 1]))
    sn = float(np.nansum(dm_neg[1: n + 1]))
    sa = float(np.nansum(atr_a[1: n + 1]))
    for i in range(n, len(c)):
        sp = sp - sp / n + dm_pos[i]
        sn = sn - sn / n + dm_neg[i]
        sa = sa - sa / n + atr_a[i]
        if sa > 0:
            di_pos[i] = 100 * sp / sa
            di_neg[i] = 100 * sn / sa

    dx = np.full(len(c), np.nan)
    valid = ~(np.isnan(di_pos) | np.isnan(di_neg))
    denom = di_pos + di_neg
    dx[valid] = np.where(denom[valid] > 0,
                         100 * np.abs(di_pos[valid] - di_neg[valid]) / denom[valid],
                         0.0)
    sdx = float(np.nanmean(dx[n: 2 * n]))
    for i in range(2 * n, len(c)):
        if not np.isnan(dx[i]):
            sdx = (sdx * (n - 1) + dx[i]) / n
            result[i] = sdx
    return result


def stochastic(
    h: np.ndarray, l: np.ndarray, c: np.ndarray, k: int = 14, d: int = 3
) -> Tuple[np.ndarray, np.ndarray]:
    pct_k = np.full(len(c), 50.0)
    for i in range(k - 1, len(c)):
        lo = float(np.min(l[i - k + 1: i + 1]))
        hi = float(np.max(h[i - k + 1: i + 1]))
        rng = hi - lo
        pct_k[i] = (c[i] - lo) / rng * 100 if rng > 0 else 50.0
    pct_d = ema(pct_k, d)
    return pct_k, pct_d


def supertrend(
    h: np.ndarray, l: np.ndarray, c: np.ndarray,
    n: int = 10, mult: float = 3.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """Returns (trend: +1/-1 array, support_line array)."""
    atr_a   = atr(h, l, c, n)
    hl2     = (h + l) / 2
    upper   = hl2 + mult * atr_a
    lower   = hl2 - mult * atr_a
    trend   = np.ones(len(c))
    st_line = lower.copy()
    for i in range(1, len(c)):
        if np.isnan(atr_a[i]):
            continue
        if trend[i - 1] == 1:
            st_line[i] = max(lower[i], st_line[i - 1])
            if c[i] < st_line[i]:
                trend[i]  = -1
                st_line[i] = upper[i]
            else:
                trend[i] = 1
        else:
            st_line[i] = min(upper[i], st_line[i - 1] if i > 0 else upper[i])
            if c[i] > st_line[i]:
                trend[i]  = 1
                st_line[i] = lower[i]
            else:
                trend[i] = -1
    return trend, st_line


def vwap(h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray) -> np.ndarray:
    tp  = (h + l + c) / 3
    cum_v  = np.cumsum(v)
    cum_tv = np.cumsum(tp * v)
    return np.where(cum_v > 0, cum_tv / cum_v, tp)


def build_feature_matrix(
    candles: list,
    label_bars: int = 3,
    label_thresh: float = 0.003,
):
    """
    Build (X, y) from a list of OHLCV dicts.
    y: +1 = price rose >= thresh in next label_bars bars
       -1 = price fell
        0 = neutral
    Returns (np.ndarray shape (N,15), np.ndarray shape (N,))
    """
    if len(candles) < 50:
        return np.empty((0, 15)), np.empty(0, dtype=int)

    c_arr = np.array([x["c"] for x in candles], dtype=float)
    h_arr = np.array([x["h"] for x in candles], dtype=float)
    l_arr = np.array([x["l"] for x in candles], dtype=float)
    v_arr = np.array([x["v"] for x in candles], dtype=float)

    rsi_a             = rsi(c_arr, 14)
    ml_arr, sl_arr, hist_arr = macd(c_arr)
    e9, e21           = ema(c_arr, 9), ema(c_arr, 21)
    bb_up, bb_md, bb_dn = bollinger(c_arr, 20)
    atr_a             = atr(h_arr, l_arr, c_arr, 14)
    adx_a             = adx(h_arr, l_arr, c_arr, 14)
    k_s, _            = stochastic(h_arr, l_arr, c_arr, 14, 3)
    st_trend, _       = supertrend(h_arr, l_arr, c_arr, 10, 3.0)

    vol_ma = np.full(len(v_arr), np.nan)
    for i in range(19, len(v_arr)):
        vol_ma[i] = float(np.mean(v_arr[i - 19: i + 1]))
    vol_ratio = v_arr / (vol_ma + 1e-9)

    bb_width  = (bb_up - bb_dn) / (bb_md + 1e-9)
    bb_pos    = (c_arr - bb_dn) / (bb_up - bb_dn + 1e-9)
    ema_diff  = (e9 - e21) / (e21 + 1e-9)
    atr_pct   = atr_a / (c_arr + 1e-9)
    mom       = c_arr / np.roll(c_arr, 5) - 1
    mom[:5]   = 0.0

    rows, labels = [], []
    start = 35
    end   = len(c_arr) - label_bars

    for i in range(start, end):
        if np.isnan(rsi_a[i]) or np.isnan(ml_arr[i]) or np.isnan(bb_up[i]) or np.isnan(adx_a[i]):
            continue
        feat = [
            rsi_a[i] / 100,
            ml_arr[i]   / (c_arr[i] + 1e-9),
            hist_arr[i] / (c_arr[i] + 1e-9),
            float(ema_diff[i]),
            float(bb_pos[i]),
            float(bb_width[i]),
            float(vol_ratio[i]),
            float(atr_pct[i]),
            float(adx_a[i]) / 100,
            float(k_s[i]) / 100,
            float(st_trend[i]),
            float(mom[i]),
            (c_arr[i] - l_arr[i]) / (h_arr[i] - l_arr[i] + 1e-9),
            (h_arr[i] - c_arr[i]) / (atr_a[i] + 1e-9),
            (c_arr[i] - l_arr[i]) / (atr_a[i] + 1e-9),
        ]
        future_ret = (c_arr[i + label_bars] - c_arr[i]) / c_arr[i]
        if future_ret > label_thresh:
            lbl = 1
        elif future_ret < -label_thresh:
            lbl = -1
        else:
            lbl = 0
        rows.append(feat)
        labels.append(lbl)

    if not rows:
        return np.empty((0, 15)), np.empty(0, dtype=int)

    return np.array(rows, dtype=float), np.array(labels, dtype=int)

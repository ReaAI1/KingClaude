"""
Aurentis AI — Hyperliquid REST API client (synchronous, requests-based).
Tested on Windows/Linux. No aiohttp SSL issues.
"""
import time
import logging
from typing import Dict, List, Optional

import requests
import urllib3

urllib3.disable_warnings()
log = logging.getLogger("aurentis.api")

_session = requests.Session()
_session.verify = False


def _post(url: str, payload: dict, timeout: int = 12) -> Optional[any]:
    try:
        r = _session.post(url, json=payload, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        log.warning("API HTTP %s: %s", r.status_code, r.text[:200])
    except Exception as exc:
        log.warning("API error: %s", exc)
    return None


def get_prices(rest_url: str) -> Dict[str, float]:
    """Return {coin: mid_price} for all perpetual coins."""
    data = _post(rest_url, {"type": "allMids"})
    if not data:
        return {}
    out: Dict[str, float] = {}
    for k, v in data.items():
        if not isinstance(k, str) or k.startswith("#"):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            pass
    return out


def get_candles(
    rest_url: str,
    coin: str,
    interval: str = "15m",
    n: int = 220,
) -> List[dict]:
    """Return last *n* OHLCV candles for *coin* at *interval*."""
    ms_map = {
        "1m":  60_000, "5m":  300_000, "15m": 900_000,
        "1h":  3_600_000, "4h": 14_400_000, "1d": 86_400_000,
    }
    ms    = ms_map.get(interval, 900_000)
    end   = int(time.time() * 1000)
    start = end - ms * (n + 10)
    data  = _post(
        rest_url,
        {
            "type": "candleSnapshot",
            "req":  {
                "coin":      coin,
                "interval":  interval,
                "startTime": start,
                "endTime":   end,
            },
        },
    )
    if not data:
        return []
    out = []
    for c in data:
        try:
            out.append({
                "t": int(c["t"]),
                "o": float(c["o"]),
                "h": float(c["h"]),
                "l": float(c["l"]),
                "c": float(c["c"]),
                "v": float(c["v"]),
            })
        except (KeyError, TypeError, ValueError):
            pass
    return out[-n:]

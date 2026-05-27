"""
Aurentis AI Trading System — Configuration
All settings are overridable via environment variables or .env file.
"""
import os
from dataclasses import dataclass, field
from typing import List
from dotenv import load_dotenv

load_dotenv()

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)

def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default

def _env_bool(key: str, default: bool) -> bool:
    v = os.environ.get(key, str(default)).lower()
    return v in ("1", "true", "yes")

def _env_list(key: str, default: str) -> List[str]:
    raw = os.environ.get(key, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


# ── Trading ───────────────────────────────────────────────────────────────────
INITIAL_CAPITAL     = _env_float("INITIAL_CAPITAL",     10_000.0)
TRADING_PAIRS       = _env_list("TRADING_PAIRS",        "BTC,ETH,SOL,DOGE,AVAX,LINK,ARB,WIF")
MAX_POSITIONS       = int(_env_float("MAX_POSITIONS",   4))
POSITION_SIZE_PCT   = _env_float("POSITION_SIZE_PCT",   0.18)   # 18% per trade
SIGNAL_THRESHOLD    = _env_float("SIGNAL_THRESHOLD",    0.24)
LOOP_SECS           = int(_env_float("LOOP_SECS",       45))

# ── Fees & Slippage ───────────────────────────────────────────────────────────
TAKER_FEE           = _env_float("TAKER_FEE",           0.00035)  # 0.035%
SLIPPAGE_BPS        = _env_float("PAPER_SLIPPAGE_BPS",  2.0)      # 2 bps

# ── Risk Management ───────────────────────────────────────────────────────────
STOP_LOSS_PCT       = _env_float("STOP_LOSS_PCT",       0.025)   # 2.5%
TAKE_PROFIT_PCT     = _env_float("TAKE_PROFIT_PCT",     0.055)   # 5.5%
PARTIAL_TP_PCT      = _env_float("PARTIAL_TP_PCT",      0.030)   # 3.0% — close half
TRAILING_STOP_PCT   = _env_float("TRAILING_STOP_PCT",   0.018)   # 1.8%
MAX_DAILY_LOSS_PCT  = _env_float("MAX_DAILY_LOSS_PCT",  5.0)     # 5%   halt threshold
MAX_WEEKLY_LOSS_PCT = _env_float("MAX_WEEKLY_LOSS_PCT", 10.0)    # 10%
MAX_DRAWDOWN_PCT    = _env_float("MAX_DRAWDOWN_PCT",    20.0)    # 20% all-time drawdown

# ── Candles ───────────────────────────────────────────────────────────────────
PRIMARY_TF          = _env("PRIMARY_TF",    "15m")
HTF_TF              = _env("HTF_TF",        "1h")
CHART_TF            = _env("CHART_TF",      "1h")
CHART_COIN          = _env("CHART_COIN",    "BTC")
CANDLE_LOOKBACK     = int(_env_float("CANDLE_LOOKBACK", 220))
HTF_LOOKBACK        = int(_env_float("HTF_LOOKBACK",    80))
CHART_BARS          = int(_env_float("CHART_BARS",      100))

# ── ML ────────────────────────────────────────────────────────────────────────
ML_RETRAIN_HOURS    = _env_float("ML_RETRAIN_HOURS",    4.0)
ML_MIN_ROWS         = int(_env_float("ML_MIN_ROWS",     80))
ML_LABEL_BARS       = int(_env_float("ML_LABEL_BARS",   3))
ML_LABEL_THRESH     = _env_float("ML_LABEL_THRESH",     0.003)   # 0.3% for label

# ── Execution Mode ────────────────────────────────────────────────────────────
EXECUTION_MODE      = _env("EXECUTION_MODE", "paper_sim")
# paper_sim   — no credentials needed, full simulation
# testnet_real — Hyperliquid testnet (requires keys)
# mainnet_real — DISABLED in v1

HL_PRIVATE_KEY      = _env("HYPERLIQUID_PRIVATE_KEY",    "")
HL_ACCOUNT_ADDRESS  = _env("HYPERLIQUID_ACCOUNT_ADDRESS","")

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH             = _env("DB_PATH",       "aurentis.db")
SUPABASE_URL        = _env("SUPABASE_URL",  "")
SUPABASE_KEY        = _env("SUPABASE_SERVICE_KEY", "")

# ── Web Dashboard ─────────────────────────────────────────────────────────────
WEB_HOST            = _env("WEB_HOST",      "0.0.0.0")
WEB_PORT            = int(os.environ.get("PORT") or _env_float("WEB_PORT", 8000))
DASHBOARD_USER      = _env("DASHBOARD_USER",     "aurentis")
DASHBOARD_PASS      = _env("DASHBOARD_PASS",     "changeme")
WS_PUSH_INTERVAL    = _env_float("WS_PUSH_INTERVAL", 3.0)   # seconds

# ── Alerts ────────────────────────────────────────────────────────────────────
DISCORD_WEBHOOK     = _env("DISCORD_WEBHOOK_URL", "")
DISCORD_ENABLED     = _env_bool("DISCORD_ENABLED", True)

# ── Hyperliquid endpoints ─────────────────────────────────────────────────────
HL_REST_URL         = "https://api.hyperliquid.xyz/info"
HL_WS_URL           = "wss://api.hyperliquid.xyz/ws"

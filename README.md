# Aurentis AI Trading System

> **Autonomous paper trading on Hyperliquid perpetuals — 24/7, from any device.**

A professional-grade algorithmic trading system built for Hyperliquid perpetuals. Combines a 10-component signal engine, LightGBM ML ensemble, adaptive weight learning, and a real-time web dashboard you can open from your phone, tablet, or any browser — anywhere.

---

## Quick Start

### Option A — Run on Windows (local network access)

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Configure**
```bash
copy .env.example .env
notepad .env
```
Set a secure password:
```env
DASHBOARD_USER=aurentis
DASHBOARD_PASS=your-secure-password
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

**3. Launch (no console window)**
Double-click **`LAUNCH DASHBOARD.vbs`**

The bot starts silently in the background and your browser opens automatically to the dashboard. Access from your phone or any device on the same Wi-Fi at `http://YOUR-PC-IP:8000`.

**4. Auto-start on boot**
Double-click **`SETUP AUTO-START.bat`** once to register with Windows Task Scheduler.

---

### Option B — 24/7 Cloud Hosting (Render.com — recommended)

No PC required. The bot runs in the cloud permanently.

**1. Push your code to GitHub**
Double-click **`PUSH TO GITHUB.bat`** (needs a GitHub Personal Access Token)

**2. Deploy to Render (free trial / $7/month for 24/7)**
1. Go to [render.com](https://render.com) → New → Web Service
2. Connect your GitHub repo (`aurentis-trader`)
3. Render auto-detects `render.yaml` — click **Deploy**
4. Set environment secrets in Render dashboard:
   - `DASHBOARD_PASS` = your password
   - `DISCORD_WEBHOOK_URL` = your webhook

Your dashboard is live at `https://aurentis-trader.onrender.com`

---

### Option C — DigitalOcean VPS ($6/month, most reliable)

```bash
# On a fresh Ubuntu 22.04 droplet:
bash scripts/setup_droplet.sh
```

Then start:
```bash
systemctl start aurentis-trader
journalctl -u aurentis-trader -f
```

Dashboard: `http://your-droplet-ip:8000`

---

## What It Does

- Connects to **Hyperliquid live prices** every 5 seconds
- Evaluates **10 trading signals** per coin on each loop
- Opens / closes **paper trades** with realistic slippage (2 bps) and taker fees (0.035%)
- Manages risk with **stop-loss, take-profit, trailing stops, partial TPs**
- **Circuit breakers** halt trading if daily/weekly losses exceed thresholds
- Sends **Discord alerts** on every trade and daily summary
- Saves all trades and portfolio snapshots to **SQLite database**
- Serves a **real-time web dashboard** — accessible from any device

---

## Signal Engine (10 Components)

Only components with an active opinion count toward the score denominator:

| Indicator | Signal on | Max contribution |
|---|---|---|
| EMA 9/21 | Crossover or sustained trend | 2.5 pts |
| RSI | Oversold < 38 or overbought > 62 | 2.5 pts |
| MACD | Signal-line crossover or momentum | 2.0 pts |
| Bollinger Bands | Price vs band position | 2.0 pts |
| Stochastic | Extreme zones only (< 25 or > 75) | 1.5 pts |
| Supertrend | Direction flip or sustained | 1.5 pts |
| Volume | Spike confirmation (> 1.8× avg) | amplifier |
| ADX | Trending market boost (> 25) | amplifier |
| LightGBM ML | Per-coin classifier, prob > 0.55 | 2.5 pts |
| HTF (1H) | Hourly trend filter | 2.0 pts |

**Signal strength** = directional points / max possible points (0–1 scale).

Trades open when strength ≥ `SIGNAL_THRESHOLD` (default 0.24).

---

## Risk Management

- **Position sizing** — 18% of portfolio per trade, scaled by signal strength
- **Stop-loss** — 2.5% from entry
- **Take-profit** — 5.5% from entry
- **Partial TP** — closes 50% at +3%, moves stop to breakeven
- **Trailing stop** — 1.8%, locks in gains as price moves favorably
- **48h time exit** — prevents stale positions
- **Circuit breakers** — daily −5% halts 4h, weekly −10% halts 24h, drawdown −20% halts 7d

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `INITIAL_CAPITAL` | `10000` | Starting capital ($) |
| `TRADING_PAIRS` | `BTC,ETH,SOL,...` | Pairs to trade |
| `SIGNAL_THRESHOLD` | `0.24` | Min signal to open trade |
| `MAX_POSITIONS` | `4` | Max simultaneous positions |
| `DASHBOARD_USER` | `aurentis` | Web login username |
| `DASHBOARD_PASS` | `changeme` | Web login password |
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord alerts webhook |

---

## Architecture

```
aurentis-trader/
├── src/
│   ├── config.py        — All settings (env vars + defaults)
│   ├── api.py           — Hyperliquid REST: prices + candles
│   ├── indicators.py    — Pure-numpy: EMA, RSI, MACD, BB, ATR, ADX, etc.
│   ├── ml_engine.py     — LightGBM classifier per coin
│   ├── signals.py       — 10-component signal engine + adaptive weights
│   ├── portfolio.py     — Paper portfolio, stops, circuit breakers
│   ├── database.py      — SQLite persistence
│   ├── alerts.py        — Discord webhook alerts
│   ├── trader.py        — TradingEngine (6 background threads)
│   ├── main.py          — Entry point
│   └── web/
│       ├── server.py         — FastAPI + WebSocket broadcaster
│       └── templates/
│           └── index.html    — Real-time dashboard
├── tests/
│   └── test_signals.py  — 21 unit tests (all passing)
├── systemd/             — Linux systemd service
├── scripts/             — DigitalOcean setup + deploy
├── .github/workflows/   — CI (auto-tests) + deploy workflow
├── render.yaml          — Render.com one-click deploy
├── railway.json         — Railway deploy config
├── fly.toml             — Fly.io deploy config
├── Procfile             — Generic cloud deploy
├── LAUNCH DASHBOARD.vbs — Windows: silent start + open browser
├── PUSH TO GITHUB.bat   — Push repo to your GitHub account
├── START AURENTIS.bat   — Windows console launcher (fallback)
└── SETUP AUTO-START.bat — Windows Task Scheduler setup
```

---

## Reliability

- Every background thread has an **outer retry loop** — no thread can permanently die
- The trading loop has **per-coin exception isolation** — one bad coin can't crash others
- **State persists** to SQLite — portfolio survives restarts if < 24h old
- **Watchdog thread** detects stale prices and force-refreshes
- **Backoff** — consecutive errors increase retry delay (up to 5 min) to avoid hammering the API
- **Windows keep-awake** — prevents PC from sleeping (SetThreadExecutionState)

---

## Running Tests

```bash
python -m pytest tests/ -v
```

21 tests covering indicators, signals, portfolio logic.

---

## Discord Alerts

Add your webhook to `.env`:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123456/abcdef
```

Alerts sent for:
- Every trade opened (with entry, stop, target, signal strength)
- Every trade closed (P&L, duration, reason)
- Circuit breaker triggers
- Daily summary at midnight

---

## Risk Warning

This system is for **paper trading only**. No real money is used. Simulated results do not guarantee real trading performance. Cryptocurrency trading carries significant risk.

---

*Built by [Aurentis AI](mailto:rea.ai.automations@gmail.com)*

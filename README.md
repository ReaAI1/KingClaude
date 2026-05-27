# Aurentis AI Trading System

> **Intelligent paper trading on Hyperliquid perpetuals — 24/7, from any device.**

A professional-grade algorithmic trading system built for Hyperliquid perpetuals. Combines a 10-component signal engine, LightGBM ML ensemble, adaptive weight learning, and a real-time web dashboard accessible from your phone, tablet, or any browser.

---

## Features

### Trading Engine
- **8 perpetual pairs** — BTC, ETH, SOL, DOGE, AVAX, LINK, ARB, WIF
- **10-component signal system** — EMA, RSI, MACD, Bollinger Bands, Stochastic, Supertrend, Volume, ADX regime, ML classifier, HTF trend filter
- **LightGBM ML** with 15 engineered features per coin, auto-retrain every 4 hours, GradientBoosting fallback
- **Adaptive weights** — each signal component tracks its own win/loss record and adjusts its contribution automatically
- **Multi-timeframe analysis** — 15-minute entry signals filtered by 1-hour trend direction
- **ADX regime detection** — trending markets boost signal confidence
- **Partial take-profit** — closes 50% at 3%, moves stop to breakeven, lets remainder run to 5.5%
- **Trailing stops** — locks in profits as price moves in your favor
- **Circuit breakers** — daily 5%, weekly 10%, drawdown 20% — auto-halts trading
- **48-hour max hold** — time-based exit prevents positions going stale

### Web Dashboard
- Beautiful dark-theme dashboard accessible from **any device on your network**
- **Live TradingView Lightweight Charts** — BTC/USDC 1H candlestick chart
- **Real-time WebSocket** — portfolio, positions, signals update every 3 seconds
- **Portfolio stats panel** — value, return %, today's P&L, win rate, Sharpe ratio, profit factor
- **Signal scanner** — live signal strength bars for all 8 coins
- **Open positions** — P&L, stop/target, signal reasons, age
- **Trade history** — full closed trade log with duration and reason
- **Equity curve** — 24-hour portfolio value chart
- **ML model status** — per-coin accuracy and training status
- **HTTP Basic Auth** — password-protected, safe to expose on your network
- **Mobile responsive** — works perfectly on iPhone/Android

### Reliability
- **Auto-restart** — .bat loop catches crashes, restarts automatically
- **Windows keep-awake** — prevents system sleep via SetThreadExecutionState
- **Task Scheduler** — auto-starts on login after reboots
- **State persistence** — SQLite survives restarts, portfolio restored if < 24h old
- **Watchdog thread** — detects stale prices and forces refresh
- **Discord alerts** — rich embeds for every trade open/close, daily summary, circuit breaker

---

## Quick Start (Windows)

### 1. Clone the repo
```bash
git clone https://github.com/rea-ai-automations/aurentis-trader.git
cd aurentis-trader
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure
```bash
copy .env.example .env
notepad .env
```

Edit `.env` at minimum:
```env
DASHBOARD_USER=aurentis
DASHBOARD_PASS=your-secure-password
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...   # optional
```

### 4. Launch
Double-click **`START AURENTIS.bat`** — or run:
```bash
python -m src.main
```

### 5. Open the dashboard
The console will print your local IP. Open from **any device**:
```
http://192.168.1.x:8000
```
Log in with your dashboard credentials.

### 6. Auto-start on boot (optional)
Double-click **`SETUP AUTO-START.bat`** to add a Task Scheduler entry.

---

## Configuration

All settings live in `.env` (copy from `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `INITIAL_CAPITAL` | `10000` | Starting paper capital ($) |
| `TRADING_PAIRS` | `BTC,ETH,SOL,...` | Comma-separated pairs |
| `SIGNAL_THRESHOLD` | `0.24` | Minimum signal strength (0–1) |
| `MAX_POSITIONS` | `4` | Max simultaneous positions |
| `DASHBOARD_USER` | `aurentis` | Web dashboard username |
| `DASHBOARD_PASS` | `changeme` | Web dashboard password |
| `WEB_PORT` | `8000` | Dashboard port |
| `DISCORD_WEBHOOK_URL` | _(empty)_ | Discord webhook for alerts |

Advanced settings are in `src/config.py`.

---

## Architecture

```
aurentis-trader/
├── src/
│   ├── config.py        — All configuration (env vars + defaults)
│   ├── api.py           — Hyperliquid REST client (prices + candles)
│   ├── indicators.py    — Pure-numpy: EMA, RSI, MACD, BB, ATR, ADX, Stoch, ST, VWAP
│   ├── ml_engine.py     — LightGBM ML classifier per coin
│   ├── signals.py       — 10-component signal engine + adaptive weights
│   ├── portfolio.py     — Paper portfolio: open/close, stops, circuit breakers
│   ├── database.py      — SQLite: trades, equity snapshots, KV state
│   ├── alerts.py        — Discord webhook alerts
│   ├── trader.py        — TradingEngine + SharedState (6 background threads)
│   ├── main.py          — Entry point
│   └── web/
│       ├── server.py    — FastAPI app + WebSocket broadcaster
│       └── templates/
│           └── index.html — Real-time dashboard (TradingView + WebSocket)
├── tests/
│   └── test_signals.py  — Unit tests for signals, indicators, portfolio
├── systemd/
│   └── aurentis-trader.service  — Linux systemd service
├── scripts/
│   ├── setup_droplet.sh — DigitalOcean Ubuntu 22.04 setup
│   └── deploy.sh        — SSH deploy script
├── .github/workflows/
│   └── deploy.yml       — GitHub Actions CI/CD
├── START AURENTIS.bat   — Windows double-click launcher
├── SETUP AUTO-START.bat — Windows Task Scheduler setup
├── requirements.txt
├── .env.example
└── pyproject.toml
```

### Background Threads

| Thread | Interval | Responsibility |
|---|---|---|
| `prices` | 5s | Fetch all prices, check stops |
| `candles` | 15min full / 5min chart | OHLCV data for all pairs |
| `trading` | 45s | Evaluate signals, open/close trades |
| `ml` | 10min check / 4h retrain | Retrain ML models |
| `snapshots` | 10min | Save equity snapshots to SQLite |
| `watchdog` | 2min | Detect stale data, keep Windows awake |

---

## Signal Engine

Each signal loop evaluates 10 components. Only components with an **active opinion** contribute to the denominator (avoids dilution from neutral indicators):

| Component | Max pts | Notes |
|---|---|---|
| EMA trend | 2.5 cross / 1.6 trending | 9/21 EMA crossover |
| RSI | 2.0 | Oversold <35 / overbought >65 |
| MACD | 2.0 | Crossover + histogram direction |
| Bollinger Bands | 1.5 | Price vs band squeeze |
| Stochastic | 1.5 | Only active in <25 / >75 zone |
| Supertrend | 1.5 cross / 1.1 trending | Direction + signal flip |
| Volume | 1.0 | Spike vs 20-bar average |
| ADX regime | ±0.3 boost | Trending amplifier |
| ML classifier | 2.5 | Only when prob > 0.55 |
| HTF (1H) | 2.0 | Only when HTF has directional bias |

**Signal strength** = (directional points) / (max possible points)

Trades open when `strength >= SIGNAL_THRESHOLD` (default 0.24).

---

## Cloud Deployment (DigitalOcean)

### 1. Create a droplet
- Ubuntu 22.04, 2 GB RAM ($12/mo or use $6/mo 1 GB)
- Add your SSH key

### 2. Run setup script
```bash
ssh root@your-droplet-ip
curl -sL https://raw.githubusercontent.com/rea-ai-automations/aurentis-trader/main/scripts/setup_droplet.sh | bash
```

### 3. Configure
```bash
nano /opt/aurentis-trader/.env
```

### 4. Start
```bash
systemctl start aurentis-trader
journalctl -u aurentis-trader -f
```

### 5. HTTPS (optional, with domain)
```bash
certbot --nginx -d yourdomain.com
```

### GitHub Actions auto-deploy
Add these secrets to your GitHub repo (`Settings > Secrets`):
- `SERVER_HOST` — your droplet IP
- `SERVER_USER` — `root` or `aurentis`
- `SERVER_SSH_KEY` — your private SSH key
- `DISCORD_WEBHOOK_URL` — optional

Every push to `main` auto-deploys.

---

## Discord Alerts

Add your webhook URL to `.env`:
```env
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/123456/abcdef
```

You'll receive:
- **Green embed** when a long trade opens
- **Red embed** when a short trade opens
- **Win/loss embed** on close with P&L, duration, reason
- **Warning embed** when circuit breaker triggers
- **Daily summary** at midnight with day P&L, win rate

---

## Running Tests

```bash
python -m pytest tests/ -v
```

---

## Risk Warning

This system is for **paper trading only**. It simulates trades without real money. Past performance of simulated systems does not guarantee real trading results. Cryptocurrency trading carries significant risk. Always do your own research before trading with real capital.

---

## License

MIT License — Copyright (c) 2024 Aurentis AI

---

*Built by [Aurentis AI](mailto:rea.ai.automations@gmail.com)*

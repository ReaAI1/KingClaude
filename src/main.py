"""
Aurentis AI — Entry point.
Starts the trading engine in background threads and launches the FastAPI web
dashboard so the system is reachable from any device on the network.
"""
import logging
import sys
import threading
import time

# ── Logging setup ─────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    datefmt= "%H:%M:%S",
    stream = sys.stdout,
)
# quiet noisy libs
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("lightgbm").setLevel(logging.WARNING)

log = logging.getLogger("aurentis.main")

from src import config as cfg
from src.database import Database
from src.alerts   import DiscordAlerter
from src.trader   import TradingEngine
from src.web      import server as web


def main():
    log.info("=" * 60)
    log.info("  Aurentis AI Trading System  v2.0")
    log.info("  Paper trading on Hyperliquid perps")
    log.info("=" * 60)
    log.info("Capital : $%,.2f", cfg.INITIAL_CAPITAL)
    log.info("Pairs   : %s",     ", ".join(cfg.TRADING_PAIRS))
    log.info("MaxPos  : %d",     cfg.MAX_POSITIONS)
    log.info("Thresh  : %.2f",   cfg.SIGNAL_THRESHOLD)
    log.info("Dashboard: http://0.0.0.0:%d  (user: %s)", cfg.WEB_PORT, cfg.DASHBOARD_USER)
    log.info("-" * 60)

    # ── Core services ──────────────────────────────────────────────────────
    db      = Database(cfg.DB_PATH)
    alerter = DiscordAlerter(cfg.DISCORD_WEBHOOK)
    engine  = TradingEngine(db, alerter)

    # ── Bootstrap (blocking — loads candles + trains ML) ──────────────────
    engine.bootstrap()

    # ── Inject engine & db into web server ────────────────────────────────
    web.init(engine, db)

    # ── Start engine threads ──────────────────────────────────────────────
    engine.start()

    # ── Run web server (blocks main thread) ───────────────────────────────
    log.info("Starting web dashboard on http://0.0.0.0:%d", cfg.WEB_PORT)
    log.info("Open from any device: http://<your-pc-ip>:%d", cfg.WEB_PORT)
    web.run(host=cfg.WEB_HOST, port=cfg.WEB_PORT)


if __name__ == "__main__":
    main()

"""
Aurentis AI — Entry point.
Starts the web server immediately (so Render health checks pass),
then bootstraps the trading engine in the background.
"""
import logging
import sys
import threading
import time

# ── Logging ───────────────────────────────────────────────────────────────
logging.basicConfig(
    level  = logging.INFO,
    format = "%(asctime)s [%(name)s] %(levelname)s  %(message)s",
    datefmt= "%H:%M:%S",
    stream = sys.stdout,
)
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
logging.getLogger("lightgbm").setLevel(logging.WARNING)

log = logging.getLogger("aurentis.main")

from src import config as cfg
from src.database import Database
from src.alerts   import DiscordAlerter
from src.trader   import TradingEngine
from src.web      import server as web


def main():
    log.info("=" * 55)
    log.info("  Aurentis AI Trading System  v2.0")
    log.info("  Capital: $%,.0f  |  Pairs: %s", cfg.INITIAL_CAPITAL, len(cfg.TRADING_PAIRS))
    log.info("=" * 55)

    db      = Database(cfg.DB_PATH)
    alerter = DiscordAlerter(cfg.DISCORD_WEBHOOK)
    engine  = TradingEngine(db, alerter)

    # Inject into web server before it starts
    web.init(engine, db)

    # Bootstrap + start engine in background thread
    # This lets the web server start immediately so cloud health checks pass
    def _start_engine():
        try:
            log.info("Bootstrapping engine (loading candles + training ML)...")
            engine.bootstrap()
            engine.start()
            log.info("Engine is LIVE — trading started.")
        except Exception as exc:
            log.error("Engine bootstrap failed: %s", exc, exc_info=True)

    t = threading.Thread(target=_start_engine, daemon=True, name="bootstrap")
    t.start()

    # Start web server immediately — dashboard shows "Starting..." until ready
    log.info("Web dashboard: http://0.0.0.0:%d", cfg.WEB_PORT)
    web.run(host=cfg.WEB_HOST, port=cfg.WEB_PORT)


if __name__ == "__main__":
    main()

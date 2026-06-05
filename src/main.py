"""
Aurentis AI — Entry point (KRONOS architecture).
Starts the web server immediately (cloud health checks), then bootstraps
KRONOS — the modular event-driven trading orchestrator — in the background.
"""
import logging
import sys
import threading

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
from src.kronos   import Kronos
from src.web      import server as web


def main():
    log.info("=" * 55)
    log.info("  Aurentis AI  //  KRONOS v3.0")
    log.info("  Capital: $%,.0f  |  Pairs: %s", cfg.INITIAL_CAPITAL, len(cfg.TRADING_PAIRS))
    log.info("=" * 55)

    db      = Database(cfg.DB_PATH)
    alerter = DiscordAlerter(cfg.DISCORD_WEBHOOK)
    kronos  = Kronos(db, alerter)

    # Inject into web server before it starts
    web.init(kronos, db)

    def _start_kronos():
        try:
            log.info("KRONOS bootstrap — loading candles + training BRAIN...")
            kronos.bootstrap()
            kronos.start()
            log.info("KRONOS ONLINE — all modules active.")
        except Exception as exc:
            log.error("KRONOS bootstrap failed: %s", exc, exc_info=True)

    threading.Thread(target=_start_kronos, daemon=True, name="bootstrap").start()

    log.info("Web dashboard: http://0.0.0.0:%d", cfg.WEB_PORT)
    web.run(host=cfg.WEB_HOST, port=cfg.WEB_PORT)


if __name__ == "__main__":
    main()

"""KronosModule — base class for every named trading system node."""
import logging
import threading
import time
from typing import Optional

from src.kronos.bus import KronosEventBus


class KronosModule:
    """
    A named, observable module with health tracking.

    Subclasses implement _run_loop() which is the module's main thread body.
    Call self.heartbeat(msg) regularly to signal liveness; call self.set_error(msg)
    on recoverable failures.
    """

    def __init__(self, name: str, bus: KronosEventBus):
        self.name = name
        self.bus = bus
        self.status = "INIT"
        self.health = "ok"       # ok | warn | error | dead
        self.last_event: Optional[str] = None
        self.last_heartbeat: float = time.time()
        self.error_count: int = 0
        self._stop_evt = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.log = logging.getLogger(f"kronos.{name.lower()}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        self._stop_evt.clear()
        self._thread = threading.Thread(
            target=self._safe_run, daemon=True, name=f"kronos.{self.name}"
        )
        self._thread.start()
        self.status = "RUNNING"
        self.log.info("Module %s started", self.name)

    def stop(self):
        self._stop_evt.set()
        self.status = "STOPPED"

    def _safe_run(self):
        try:
            self._run_loop()
        except Exception as exc:
            self.health = "dead"
            self.status = "CRASHED"
            self.last_event = f"FATAL: {exc}"
            self.log.error("Module %s crashed: %s", self.name, exc, exc_info=True)

    def _run_loop(self):
        raise NotImplementedError

    # ── Observability helpers ─────────────────────────────────────────────────

    def heartbeat(self, msg: str = ""):
        self.last_heartbeat = time.time()
        self.health = "ok"
        self.error_count = max(0, self.error_count - 1)
        if msg:
            self.last_event = msg

    def set_error(self, msg: str):
        self.error_count += 1
        self.health = "error" if self.error_count > 5 else "warn"
        self.last_event = f"ERR: {msg[:100]}"
        self.log.warning("%s error (%d): %s", self.name, self.error_count, msg)

    # ── Event helpers ─────────────────────────────────────────────────────────

    def publish(self, topic: str, data=None):
        self.bus.publish(topic, data, source=self.name)

    def subscribe(self, topic: str, handler):
        self.bus.subscribe(topic, handler)

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        age = time.time() - self.last_heartbeat
        health = self.health
        if self.status == "RUNNING":
            if age > 300:
                health = "dead"
            elif age > 90 and health == "ok":
                health = "warn"
        return {
            "name":       self.name,
            "status":     self.status,
            "health":     health,
            "last_event": self.last_event or "—",
            "errors":     self.error_count,
            "age_secs":   round(age),
        }

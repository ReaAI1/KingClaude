"""
Aurentis AI — FastAPI web dashboard server.
Accessible from any device on the network (phone, tablet, laptop).
Protected by HTTP Basic Auth.
WebSocket pushes live updates every 3 seconds.
"""
import asyncio
import json
import logging
import secrets
import time
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
import uvicorn

from src import config as cfg

log = logging.getLogger("aurentis.web")

app        = FastAPI(title="Aurentis AI Trading System", docs_url=None, redoc_url=None)
security   = HTTPBasic()
templates  = Jinja2Templates(directory="src/web/templates")

# Injected by main.py
_engine    = None
_db        = None


def init(engine, db):
    global _engine, _db
    _engine = engine
    _db     = db


# ── Auth ──────────────────────────────────────────────────────────────────────
def require_auth(creds: HTTPBasicCredentials = Depends(security)):
    ok_user = secrets.compare_digest(creds.username.encode(), cfg.DASHBOARD_USER.encode())
    ok_pass = secrets.compare_digest(creds.password.encode(), cfg.DASHBOARD_PASS.encode())
    if not (ok_user and ok_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return creds.username


# ── Pages ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _=Depends(require_auth)):
    return templates.TemplateResponse("index.html", {
        "request":        request,
        "company":        "Aurentis AI",
        "version":        "v2.0",
        "dashboard_user": cfg.DASHBOARD_USER,
        "dashboard_pass": cfg.DASHBOARD_PASS,
    })


# ── REST API ──────────────────────────────────────────────────────────────────
@app.get("/api/state")
async def api_state(_=Depends(require_auth)):
    if not _engine:
        return JSONResponse({"error": "engine not ready"}, status_code=503)
    prices  = _engine.state.prices
    st      = _engine.portfolio.stats(prices)
    return {
        "portfolio":  st,
        "positions":  _engine.portfolio.open_positions_list(prices),
        "trades":     _engine.portfolio.recent_trades_list(20),
        "signals":    _engine.state.snapshot()["signals"],
        "status":     _engine.state.status,
        "uptime":     _engine.state.uptime,
        "prices":     {k: v for k, v in prices.items() if k in cfg.TRADING_PAIRS},
        "ml_summary": _engine.ml.summary(),
        "weights":    _engine.state.signals,   # placeholder
        "timestamp":  time.time(),
    }


@app.get("/api/equity")
async def api_equity(hours: int = 24, _=Depends(require_auth)):
    if not _db:
        return []
    return _db.equity_curve(hours)


@app.get("/api/trades")
async def api_trades(n: int = 100, _=Depends(require_auth)):
    if not _db:
        return []
    return _db.recent_trades(n)


@app.get("/api/candles")
async def api_candles(coin: str = "BTC", tf: str = "1h", _=Depends(require_auth)):
    if not _engine:
        return []
    with _engine.state._lock:
        c = list(_engine.state.chart_candles)
    return c


@app.get("/api/health")
async def health():
    return {"status": "ok", "ts": time.time()}


# ── WebSocket live feed ───────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self._active = []
        self._lock   = asyncio.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self._lock:
            self._active.append(ws)

    async def disconnect(self, ws: WebSocket):
        async with self._lock:
            if ws in self._active:
                self._active.remove(ws)

    async def broadcast(self, data: dict):
        payload = json.dumps(data)
        async with self._lock:
            dead = []
            for ws in self._active:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self._active.remove(ws)

    def count(self) -> int:
        return len(self._active)


_mgr = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    # Basic auth via query param token for WebSocket
    token = ws.query_params.get("token", "")
    expected = cfg.DASHBOARD_USER + ":" + cfg.DASHBOARD_PASS
    if token != expected:
        await ws.close(code=4001)
        return

    await _mgr.connect(ws)
    log.info("WS client connected (%d active)", _mgr.count())
    try:
        while True:
            await asyncio.sleep(cfg.WS_PUSH_INTERVAL)
            if not _engine:
                continue
            prices = _engine.state.prices
            st     = _engine.portfolio.stats(prices)
            data   = {
                "type":       "update",
                "ts":         time.time(),
                "portfolio":  st,
                "positions":  _engine.portfolio.open_positions_list(prices),
                "trades":     _engine.portfolio.recent_trades_list(15),
                "signals":    _engine.state.snapshot()["signals"],
                "prices":     {k: v for k, v in prices.items() if k in cfg.TRADING_PAIRS},
                "status":     _engine.state.status,
                "uptime":     _engine.state.uptime,
                "ml_summary": _engine.ml.summary(),
            }
            await _mgr.broadcast(data)
    except WebSocketDisconnect:
        pass
    finally:
        await _mgr.disconnect(ws)
        log.info("WS client disconnected (%d active)", _mgr.count())


def run(host: str = "0.0.0.0", port: int = 8000):
    uvicorn.run(app, host=host, port=port, log_level="warning")

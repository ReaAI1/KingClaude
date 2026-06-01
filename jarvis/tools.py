#!/usr/bin/env python3
"""
Mean Jarvis — Tool definitions and executors.
All tool methods are safe to call even when external systems are offline.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

# ── Tool Definitions ──────────────────────────────────────────────────────────

CLAUDE_TOOLS = [
    {
        "name": "get_portfolio_status",
        "description": "Get current portfolio value, cash, P&L, win rate, Sharpe ratio, open positions count. Call this for any portfolio/account question.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_open_positions",
        "description": "Get list of all currently open trading positions with entry price, P&L, stop loss, take profit.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_recent_trades",
        "description": "Get recently closed trades.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of trades (default 10)", "default": 10}
            },
            "required": []
        }
    },
    {
        "name": "get_coin_price",
        "description": "Get live price of a cryptocurrency.",
        "input_schema": {
            "type": "object",
            "properties": {
                "coin": {"type": "string", "description": "Coin symbol e.g. BTC, ETH, SOL"}
            },
            "required": ["coin"]
        }
    },
    {
        "name": "get_trading_signals",
        "description": "Get current buy/sell signals for all tracked coins with strength and reasons.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "get_trading_engine_status",
        "description": "Check if trading bot is running, uptime, loop count, current status.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    },
    {
        "name": "run_n8n_workflow",
        "description": "Trigger an n8n automation workflow by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "workflow_name": {"type": "string", "description": "Name of the n8n workflow/webhook to trigger"},
                "data": {"type": "object", "description": "Optional data payload to send"}
            },
            "required": ["workflow_name"]
        }
    },
    {
        "name": "read_client_data",
        "description": "Read client data from Google Sheets or a configured spreadsheet.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What information to look for e.g. 'all clients', 'client named John', 'overdue payments'"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "remember",
        "description": "Store a piece of information persistently so Jarvis remembers it in future sessions.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short label for what's being stored"},
                "value": {"type": "string", "description": "The information to remember"}
            },
            "required": ["key", "value"]
        }
    },
    {
        "name": "recall",
        "description": "Recall previously stored information. If no key given, lists all stored memories.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "The label to look up (optional)"}
            },
            "required": []
        }
    },
    {
        "name": "get_current_time",
        "description": "Get current date and time.",
        "input_schema": {"type": "object", "properties": {}, "required": []}
    }
]

# ── Tool Display Labels ───────────────────────────────────────────────────────

TOOL_DISPLAY = {
    "get_portfolio_status": "Checking portfolio...",
    "get_open_positions": "Fetching open positions...",
    "get_recent_trades": "Loading trade history...",
    "get_coin_price": "Getting live price...",
    "get_trading_signals": "Reading trading signals...",
    "get_trading_engine_status": "Checking trading bot...",
    "run_n8n_workflow": "Triggering automation...",
    "read_client_data": "Reading client data...",
    "remember": "Saving to memory...",
    "recall": "Retrieving from memory...",
    "get_current_time": "Checking time...",
}

# ── MemoryStore ───────────────────────────────────────────────────────────────

class MemoryStore:
    """JSON file-backed persistent key-value store."""

    def __init__(self, filepath: str = None):
        if filepath is None:
            filepath = str(Path(__file__).parent / "jarvis_memory.json")
        self._path = Path(filepath)
        self._data: dict = {}
        self._load()

    def _load(self):
        try:
            if self._path.exists():
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            self._data = {}

    def _save(self):
        try:
            self._path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")
        except Exception:
            pass

    def set(self, key: str, value: str):
        self._data[key] = value
        self._save()

    def get(self, key: str):
        return self._data.get(key)

    def all(self) -> dict:
        return dict(self._data)

# ── TradingAPIClient ──────────────────────────────────────────────────────────

class TradingAPIClient:
    """Calls the trading system REST API."""

    def __init__(self, api_url: str = None):
        if api_url is None:
            api_url = os.environ.get("TRADING_API_URL", "http://localhost:8000")
        self.api_url = api_url.rstrip("/")
        self._cached_snapshot = None

    def snapshot(self) -> dict:
        try:
            r = requests.get(f"{self.api_url}/api/snapshot", timeout=5)
            r.raise_for_status()
            data = r.json()
            self._cached_snapshot = data
            return data
        except Exception as e:
            return {"error": str(e), "offline": True}

    def get_portfolio(self) -> dict:
        snap = self.snapshot()
        if snap.get("offline") or snap.get("error"):
            return snap
        return snap.get("stats", snap.get("portfolio", snap))

    def get_positions(self) -> list:
        snap = self.snapshot()
        if snap.get("offline") or snap.get("error"):
            return [snap]
        positions = snap.get("positions", snap.get("open_positions", []))
        if isinstance(positions, list):
            return positions
        return [{"error": "Unexpected positions format", "raw": str(positions)}]

    def get_signals(self) -> dict:
        snap = self.snapshot()
        if snap.get("offline") or snap.get("error"):
            return snap
        return snap.get("signals", snap.get("trading_signals", {}))

    def get_prices(self) -> dict:
        snap = self.snapshot()
        if snap.get("offline") or snap.get("error"):
            return snap
        return snap.get("prices", snap.get("market_prices", {}))

    def get_status(self) -> dict:
        snap = self.snapshot()
        if snap.get("offline") or snap.get("error"):
            return snap
        return {
            "running": snap.get("running", snap.get("bot_running", False)),
            "uptime": snap.get("uptime", snap.get("uptime_seconds", 0)),
            "loop_count": snap.get("loop_count", snap.get("loops", 0)),
            "status": snap.get("status", "unknown"),
        }

# ── N8nClient ─────────────────────────────────────────────────────────────────

class N8nClient:
    """Triggers n8n automation workflows via webhooks."""

    def __init__(self):
        raw = os.environ.get("N8N_WEBHOOKS", "")
        self._webhooks: dict = {}
        if raw:
            try:
                self._webhooks = json.loads(raw)
            except Exception:
                self._webhooks = {}

    def trigger(self, workflow_name: str, data: dict = None) -> dict:
        if data is None:
            data = {}
        if workflow_name not in self._webhooks:
            available = list(self._webhooks.keys())
            return {
                "error": f"Workflow '{workflow_name}' not found.",
                "available": available,
                "hint": "Configure N8N_WEBHOOKS in .env as JSON: {\"workflow_name\": \"webhook_url\"}"
            }
        url = self._webhooks[workflow_name]
        try:
            r = requests.post(url, json=data, timeout=10)
            return {"triggered": True, "workflow": workflow_name, "response": r.text[:500]}
        except Exception as e:
            return {"error": str(e), "workflow": workflow_name}

    def list_workflows(self) -> list:
        return list(self._webhooks.keys())

# ── GoogleSheetsClient ────────────────────────────────────────────────────────

class GoogleSheetsClient:
    """Reads data from Google Sheets via gspread."""

    def __init__(self):
        self._creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "")
        self._sheet_id = os.environ.get("DEFAULT_SHEET_ID", "")

    def read(self, query: str) -> dict:
        try:
            import gspread
            from google.oauth2.service_account import Credentials
        except ImportError:
            return {"error": "gspread not installed - run: pip install gspread google-auth"}

        if not self._creds_path:
            return {"error": "GOOGLE_CREDENTIALS_PATH not configured in .env"}

        if not self._sheet_id:
            return {"error": "DEFAULT_SHEET_ID not configured in .env"}

        try:
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = Credentials.from_service_account_file(self._creds_path, scopes=scopes)
            gc = gspread.authorize(creds)
            sheet = gc.open_by_key(self._sheet_id).sheet1
            records = sheet.get_all_records()
            return {"data": records, "count": len(records), "query": query}
        except Exception as e:
            return {"error": str(e)}

# ── Tool Router ───────────────────────────────────────────────────────────────

def execute_tool(
    name: str,
    inputs: dict,
    trading: TradingAPIClient,
    n8n: N8nClient,
    sheets: GoogleSheetsClient,
    memory: MemoryStore,
) -> str:
    """Route tool calls and return a JSON string result."""

    try:
        result = _dispatch(name, inputs, trading, n8n, sheets, memory)
    except Exception as e:
        result = {"error": f"Tool execution error: {str(e)}"}

    return json.dumps(result, default=str)


def _dispatch(name, inputs, trading, n8n, sheets, memory):
    if name == "get_portfolio_status":
        return trading.get_portfolio()

    elif name == "get_open_positions":
        positions = trading.get_positions()
        if isinstance(positions, dict) and positions.get("error"):
            return positions
        return {"positions": positions, "count": len(positions)}

    elif name == "get_recent_trades":
        snap = trading.snapshot()
        if snap.get("offline") or snap.get("error"):
            return snap
        limit = inputs.get("limit", 10)
        trades = snap.get("recent_trades", snap.get("closed_trades", []))
        if isinstance(trades, list):
            return {"trades": trades[:limit], "shown": min(limit, len(trades)), "total": len(trades)}
        return {"trades": [], "note": "No trade history available"}

    elif name == "get_coin_price":
        coin = inputs.get("coin", "").upper()
        if not coin:
            return {"error": "No coin symbol provided"}
        prices = trading.get_prices()
        if isinstance(prices, dict) and prices.get("error"):
            return prices
        price = prices.get(coin, prices.get(coin.lower()))
        if price is None:
            available = list(prices.keys()) if isinstance(prices, dict) else []
            return {
                "error": f"Price for {coin} not found",
                "available_coins": available[:10],
            }
        try:
            price_float = float(price)
            formatted = f"${price_float:,.2f}"
        except (ValueError, TypeError):
            formatted = str(price)
        return {"coin": coin, "price": price, "formatted": formatted}

    elif name == "get_trading_signals":
        signals = trading.get_signals()
        return signals if signals else {"note": "No signals available"}

    elif name == "get_trading_engine_status":
        return trading.get_status()

    elif name == "run_n8n_workflow":
        workflow_name = inputs.get("workflow_name", "")
        data = inputs.get("data", {})
        if not workflow_name:
            return {"error": "workflow_name is required"}
        available = n8n.list_workflows()
        if not available:
            return {
                "error": "N8N_WEBHOOKS not configured",
                "hint": 'Add to .env: N8N_WEBHOOKS={"workflow_name": "https://your-n8n.com/webhook/abc"}'
            }
        return n8n.trigger(workflow_name, data)

    elif name == "read_client_data":
        query = inputs.get("query", "all data")
        return sheets.read(query)

    elif name == "remember":
        key = inputs.get("key", "").strip()
        value = inputs.get("value", "").strip()
        if not key:
            return {"error": "key is required"}
        memory.set(key, value)
        return {"stored": True, "key": key, "value": value}

    elif name == "recall":
        key = inputs.get("key", "").strip()
        if not key:
            all_memories = memory.all()
            if not all_memories:
                return {"memories": {}, "note": "No memories stored yet"}
            return {"memories": all_memories, "count": len(all_memories)}
        value = memory.get(key)
        if value is None:
            all_keys = list(memory.all().keys())
            return {"found": False, "key": key, "available_keys": all_keys}
        return {"found": True, "key": key, "value": value}

    elif name == "get_current_time":
        now = datetime.now()
        return {
            "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day": now.strftime("%A"),
        }

    else:
        return {"error": f"Unknown tool: {name}"}

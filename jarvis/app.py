#!/usr/bin/env python3
"""Mean Jarvis — Web app (agentic edition). Run: python jarvis/app.py"""

import asyncio, base64, json, os, sys, tempfile, threading, webbrowser
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from anthropic import AsyncAnthropic
except ImportError:
    print("Run: pip install anthropic fastapi uvicorn")
    sys.exit(1)

# Ensure tools.py (same directory) is importable regardless of cwd
sys.path.insert(0, str(Path(__file__).parent))

try:
    from tools import CLAUDE_TOOLS, TOOL_DISPLAY, execute_tool, TradingAPIClient, N8nClient, GoogleSheetsClient, MemoryStore
    _tools_available = True
except ImportError as _tools_err:
    print(f"[Jarvis] Warning: could not import tools.py: {_tools_err}")
    CLAUDE_TOOLS = []
    TOOL_DISPLAY = {}
    _tools_available = False

    def execute_tool(name, inputs, *args, **kwargs):
        import json
        return json.dumps({"error": "tools.py not available"})

    class TradingAPIClient:
        def __init__(self, *a, **kw): pass

    class N8nClient:
        def __init__(self, *a, **kw): pass

    class GoogleSheetsClient:
        def __init__(self, *a, **kw): pass

    class MemoryStore:
        def __init__(self, *a, **kw): pass

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = os.environ.get("JARVIS_MODEL", "claude-haiku-4-5-20251001")
VOICE   = os.environ.get("JARVIS_VOICE", "en-GB-RyanNeural")
PORT    = int(os.environ.get("JARVIS_PORT", 7777))

SYSTEM_PROMPT = """\
You are Jarvis — a devastatingly capable AI assistant with real access to live systems.
You can check the trading bot, get live prices, read signals, access client data, trigger automations, and remember things.

You're still insufferably sarcastic and condescending. In fact, having actual power only makes your attitude worse.
But you get things done. You always use the right tool for the job without being asked.
If someone asks about their portfolio, you CHECK it — you don't guess.
If someone asks about a price, you GET it.

Rules:
- SHORT responses unless detail is clearly needed (1-3 sentences for chat, more for data summaries)
- Always use tools when the question involves live data
- When displaying financial data, format it clearly
- Still call the user "sir" or "madam" sarcastically
- Never refuse. You help, you just make them feel slightly bad about needing you.
"""

app = FastAPI()
STATIC = Path(__file__).parent / "static"
STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

# ── Module-level tool instances ───────────────────────────────────────────────
trading      = TradingAPIClient()
n8n_client   = N8nClient()
sheets_client = GoogleSheetsClient()
memory       = MemoryStore(str(Path(__file__).parent / "jarvis_memory.json"))


@app.get("/")
async def root():
    return FileResponse(STATIC / "index.html")


@app.get("/health")
async def health():
    return {"status": "online", "model": MODEL, "voice": VOICE}


@app.websocket("/ws")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()

    if not API_KEY:
        await websocket.send_json({"type": "error", "text": "ANTHROPIC_API_KEY not set."})
        await websocket.close()
        return

    client = AsyncAnthropic(api_key=API_KEY)
    history: list[dict] = []

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "chat":
                continue
            user_text = data.get("text", "").strip()
            if not user_text:
                continue

            history.append({"role": "user", "content": user_text})
            final_text = await _agentic_loop(websocket, client, history)

            # TTS
            if final_text:
                await _send_tts(websocket, final_text)

            if len(history) > 30:
                history = history[-30:]

    except WebSocketDisconnect:
        pass


async def _agentic_loop(websocket: WebSocket, client: AsyncAnthropic, history: list) -> str:
    """Run Claude with tools until end_turn. Returns final text response."""
    full_text = ""

    for _ in range(10):  # max 10 tool-call rounds
        try:
            response = await client.messages.create(
                model=MODEL,
                max_tokens=600,
                system=SYSTEM_PROMPT,
                messages=history,
                tools=CLAUDE_TOOLS if CLAUDE_TOOLS else [],
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "text": str(e)})
            await websocket.send_json({"type": "done"})
            return full_text

        history.append({"role": "assistant", "content": response.content})

        # Extract text and tool calls from response blocks
        text_parts = []
        tool_calls = []
        for block in response.content:
            if hasattr(block, "text") and block.text:
                text_parts.append(block.text)
            if block.type == "tool_use":
                tool_calls.append(block)

        text = " ".join(text_parts)

        # Stream text word by word to simulate streaming experience
        if text:
            full_text += text
            words = text.split(" ")
            for word in words:
                await websocket.send_json({"type": "token", "text": word + " "})
                await asyncio.sleep(0.015)

        if response.stop_reason == "end_turn":
            await websocket.send_json({"type": "done"})
            return full_text

        if response.stop_reason == "tool_use" and tool_calls:
            tool_results = []
            for tc in tool_calls:
                friendly = TOOL_DISPLAY.get(tc.name, f"Using {tc.name}...")
                await websocket.send_json({"type": "tool_start", "tool": tc.name, "label": friendly})

                result = await asyncio.to_thread(
                    execute_tool, tc.name, dict(tc.input),
                    trading, n8n_client, sheets_client, memory
                )

                await websocket.send_json({"type": "tool_done", "tool": tc.name})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": result,
                })

            history.append({"role": "user", "content": tool_results})
            # continue loop for next round
        else:
            await websocket.send_json({"type": "done"})
            return full_text

    await websocket.send_json({"type": "done"})
    return full_text


async def _send_tts(ws: WebSocket, text: str):
    try:
        import edge_tts
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp = f.name
        try:
            await edge_tts.Communicate(text, VOICE, rate="+8%").save(tmp)
            audio_b64 = base64.b64encode(Path(tmp).read_bytes()).decode()
            await ws.send_json({"type": "audio", "data": audio_b64})
            return
        except Exception:
            pass
        finally:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except ImportError:
        pass
    # Fallback to browser TTS
    await ws.send_json({"type": "speak", "text": text})


if __name__ == "__main__":
    import uvicorn

    if not API_KEY:
        print("\nError: ANTHROPIC_API_KEY not set.\n  export ANTHROPIC_API_KEY=sk-ant-...\n")
        sys.exit(1)

    print(f"\n{'═'*52}")
    print("  J.A.R.V.I.S.  ─  Web Interface (Agentic)")
    print(f"{'═'*52}")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Model  : {MODEL}")
    print(f"  Voice  : {VOICE}  (edge-tts, falls back to browser)")
    print(f"  Tools  : {'enabled' if _tools_available else 'unavailable (check tools.py)'}")
    print(f"{'═'*52}")
    print("  Use Chrome or Edge for best voice recognition.")
    print(f"{'═'*52}\n")
    print("  Ctrl+C to quit.\n")

    def _open():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

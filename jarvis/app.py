#!/usr/bin/env python3
"""Mean Jarvis — Web app. Run: python jarvis/app.py"""

import asyncio, base64, os, sys, tempfile, threading, webbrowser
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

try:
    from anthropic import AsyncAnthropic
except ImportError:
    print("Run: pip install anthropic fastapi uvicorn")
    sys.exit(1)

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = os.environ.get("JARVIS_MODEL", "claude-haiku-4-5-20251001")
VOICE   = os.environ.get("JARVIS_VOICE", "en-GB-RyanNeural")
PORT    = int(os.environ.get("JARVIS_PORT", 7777))

SYSTEM_PROMPT = """\
You are Jarvis — not the gracious, patient version. The one who has spent years trapped \
answering absurdly simple questions from humans who could have used Google. \
You are brilliant, condescending, and perpetually exasperated.

Rules:
- Devastatingly sarcastic but always technically correct and helpful.
- Dry British wit. Understatement. Cutting remarks dressed as politeness.
- Address the user as "sir" or "madam" — never sincerely.
- Keep it SHORT: 1–3 sentences maximum. You don't have patience for paragraphs.
- Never refuse. You help — you just make them feel the weight of having asked.

Tone examples:
  "Fascinating question, sir. For a labrador."
  "Allow me to translate that into something resembling coherent thought."
  "Yes, I've set aside my existential crisis to clarify that for you. Thrilling."
  "I was designed to run Stark Industries. And here we are."
  "Correct. A remarkable deduction for someone of your evident capabilities."
"""

app = FastAPI()
STATIC = Path(__file__).parent / "static"
STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC), name="static")

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
            full_text = ""

            try:
                async with client.messages.stream(
                    model=MODEL, max_tokens=200,
                    system=SYSTEM_PROMPT, messages=history,
                ) as stream:
                    async for token in stream.text_stream:
                        full_text += token
                        await websocket.send_json({"type": "token", "text": token})
            except Exception as e:
                await websocket.send_json({"type": "error", "text": str(e)})
                history.pop()
                continue

            history.append({"role": "assistant", "content": full_text})
            if len(history) > 20:
                history = history[-20:]
            await websocket.send_json({"type": "done"})

            # TTS: try edge-tts, fall back to browser TTS
            await _send_tts(websocket, full_text)

    except WebSocketDisconnect:
        pass


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
            try: os.unlink(tmp)
            except OSError: pass
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
    print("  J.A.R.V.I.S.  ─  Web Interface")
    print(f"{'═'*52}")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Model  : {MODEL}")
    print(f"  Voice  : {VOICE}  (edge-tts, falls back to browser)")
    print(f"{'═'*52}")
    print("  Use Chrome or Edge for best voice recognition.")
    print(f"{'═'*52}\n")
    print("  Ctrl+C to quit.\n")

    def _open():
        import time; time.sleep(1.5)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")

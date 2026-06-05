#!/usr/bin/env python3
"""
Mean Jarvis — Launcher
Run this to start Jarvis. It will:
  1. Start the web server at http://localhost:7777
  2. Add a system tray icon
  3. Open your browser automatically
  4. Keep running until you quit from the tray

Usage:
    python jarvis/launcher.py
"""

import os, sys, threading, time, webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def check_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        print("\n" + "="*55)
        print("  ERROR: ANTHROPIC_API_KEY not set")
        print("="*55)
        print("  Set it before running:")
        print("  Windows: set ANTHROPIC_API_KEY=sk-ant-...")
        print("  Mac/Linux: export ANTHROPIC_API_KEY=sk-ant-...")
        print("  Or add it to jarvis/.env")
        print("="*55 + "\n")
        sys.exit(1)


def load_dotenv():
    """Load .env (or .env.example) from jarvis directory if present."""
    jarvis_dir = Path(__file__).parent
    for name in (".env", ".env.example"):
        env_path = jarvis_dir / name
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break


def main():
    load_dotenv()
    check_api_key()

    PORT = int(os.environ.get("JARVIS_PORT", 7777))

    print(f"\n{'═'*55}")
    print("  J.A.R.V.I.S.  —  Starting up")
    print(f"{'═'*55}")
    print(f"  URL    : http://localhost:{PORT}")
    print(f"  Model  : {os.environ.get('JARVIS_MODEL', 'claude-haiku-4-5-20251001')}")
    print(f"{'═'*55}")
    print("  System tray icon will appear shortly.")
    print("  Browser opens automatically.")
    print("  To quit: right-click tray icon → Quit")
    print(f"{'═'*55}\n")

    # Start tray in background thread
    from tray import run_tray
    tray_thread = threading.Thread(target=run_tray, args=(PORT,), daemon=True)
    tray_thread.start()

    # Open browser after server starts
    def _open():
        time.sleep(2.5)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=_open, daemon=True).start()

    # Start FastAPI server (blocks)
    import uvicorn
    import importlib.util
    spec = importlib.util.spec_from_file_location("app", Path(__file__).parent / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    uvicorn.run(mod.app, host="0.0.0.0", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()

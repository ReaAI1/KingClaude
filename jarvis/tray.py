#!/usr/bin/env python3
"""System tray icon for Mean Jarvis — keeps it running in background."""

import webbrowser
import threading


def run_tray(port: int = 7777, stop_event: threading.Event = None):
    """Start system tray icon. Call from a daemon thread."""
    try:
        import pystray
        from PIL import Image, ImageDraw
    except ImportError:
        print("[Tray] Install pystray and Pillow: pip install pystray Pillow")
        return

    # Create a simple cyan circle icon
    def make_icon():
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 60, 60], fill=(0, 180, 216, 255))
        d.ellipse([16, 16, 48, 48], fill=(0, 20, 40, 255))
        d.ellipse([24, 24, 40, 40], fill=(0, 180, 216, 200))
        return img

    def open_jarvis(icon, item):
        webbrowser.open(f"http://localhost:{port}")

    def quit_jarvis(icon, item):
        icon.stop()
        if stop_event:
            stop_event.set()
        import os, signal
        os.kill(os.getpid(), signal.SIGTERM)

    icon = pystray.Icon(
        "jarvis",
        make_icon(),
        "J.A.R.V.I.S. — Online",
        menu=pystray.Menu(
            pystray.MenuItem("Open Jarvis", open_jarvis, default=True),
            pystray.MenuItem("Quit", quit_jarvis),
        )
    )
    icon.run()

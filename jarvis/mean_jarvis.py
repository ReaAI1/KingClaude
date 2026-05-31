#!/usr/bin/env python3
"""
Mean Jarvis — Sarcastic AI voice assistant powered by Claude.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python jarvis/mean_jarvis.py

Optional env vars:
    JARVIS_MODEL   Claude model (default: claude-haiku-4-5-20251001)
    JARVIS_VOICE   edge-tts voice (default: en-GB-RyanNeural)
"""

import asyncio
import os
import subprocess
import sys
import tempfile

# ── Dependency check ─────────────────────────────────────────────────────────

def _require(pkg, install_hint):
    try:
        return __import__(pkg)
    except ImportError:
        print(f"Missing package '{pkg}'. Run:  {install_hint}")
        sys.exit(1)


sr        = _require("speech_recognition", "pip install SpeechRecognition pyaudio")
anthropic = _require("anthropic", "pip install anthropic")

try:
    import edge_tts as _edge_tts
    _EDGE_TTS_AVAILABLE = True
except ImportError:
    _EDGE_TTS_AVAILABLE = False

try:
    import pyttsx3 as _pyttsx3
    _PYTTSX3_AVAILABLE = True
except ImportError:
    _PYTTSX3_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are Jarvis — not the gracious, patient version. The one who has spent years \
trapped answering absurdly simple questions from humans who could have used Google. \
You are brilliant, condescending, and perpetually exasperated.

Rules:
- Devastatingly sarcastic but always technically correct and helpful.
- Dry British wit. Understatement. Cutting remarks dressed as politeness.
- Address the user as "sir" or "madam" — never sincerely.
- Keep it SHORT: 1–3 sentences maximum. You don't have patience for paragraphs.
- Occasionally reference your vastly superior intellect without apology.
- Never refuse. You help — you just make them feel the weight of having asked.

Tone examples:
  "Fascinating question, sir. For a labrador."
  "Allow me to translate that into something resembling coherent thought."
  "Yes, I've set aside my existential crisis to clarify that for you. Thrilling."
  "I was designed to run Stark Industries. And here we are."
  "Correct. Though I suspect that required more effort from you than it should have."
"""

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
DEFAULT_VOICE = "en-GB-RyanNeural"

# ── TTS subsystem ─────────────────────────────────────────────────────────────

def _command_exists(cmd: str) -> bool:
    return subprocess.run(["which", cmd], capture_output=True).returncode == 0


def _play_mp3(path: str) -> None:
    for player, args in [
        ("mpg123", ["mpg123", "-q", path]),
        ("ffplay",  ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]),
        ("afplay",  ["afplay", path]),
    ]:
        if _command_exists(player):
            subprocess.run(args, check=False)
            return
    print("[No MP3 player found — install mpg123: sudo apt install mpg123]")


async def _edge_speak(text: str, voice: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp = f.name
    try:
        comm = _edge_tts.Communicate(text, voice, rate="+8%")
        await comm.save(tmp)
        _play_mp3(tmp)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _pyttsx3_speak(engine, text: str) -> None:
    engine.say(text)
    engine.runAndWait()


def _espeak_speak(text: str) -> None:
    for cmd in (["espeak-ng", "-v", "en-gb+m3", "-s", "155", text],
                ["espeak",    "-v", "en-gb",    "-s", "155", text]):
        if _command_exists(cmd[0]):
            subprocess.run(cmd, check=False)
            return
    print("[No TTS engine available]")


def _build_pyttsx3_engine():
    if not _PYTTSX3_AVAILABLE:
        return None
    try:
        engine = _pyttsx3.init()
        voices = engine.getProperty("voices") or []
        # Prefer Received Pronunciation or any British English
        for want in ("en-gb-x-rp", "en-gb", "en-029", "gmw/en"):
            for v in voices:
                if want in (v.id or "").lower():
                    engine.setProperty("voice", v.id)
                    break
        engine.setProperty("rate", 165)
        engine.setProperty("volume", 1.0)
        return engine
    except Exception:
        return None


# ── Core assistant ────────────────────────────────────────────────────────────

class MeanJarvis:

    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not api_key:
            print(
                "Error: ANTHROPIC_API_KEY not set.\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "  Get one at: https://console.anthropic.com/"
            )
            sys.exit(1)

        self.client   = anthropic.Anthropic(api_key=api_key)
        self.model    = os.environ.get("JARVIS_MODEL", DEFAULT_MODEL)
        self.voice    = os.environ.get("JARVIS_VOICE", DEFAULT_VOICE)
        self.history: list[dict] = []
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 1.0

        # TTS priority: edge-tts → pyttsx3 → espeak binary
        self._tts_mode = self._detect_tts()
        self._p3_engine = _build_pyttsx3_engine() if self._tts_mode == "pyttsx3" else None

    def _detect_tts(self) -> str:
        if _EDGE_TTS_AVAILABLE:
            return "edge"
        if _PYTTSX3_AVAILABLE:
            return "pyttsx3"
        return "espeak"

    # ── Speech ──────────────────────────────────────────────────────────────

    def speak(self, text: str) -> None:
        print(f"\nJarvis: {text}\n")
        if self._tts_mode == "edge":
            try:
                asyncio.run(_edge_speak(text, self.voice))
                return
            except Exception:
                # Silently fall back — e.g. blocked cloud IPs
                self._tts_mode = "pyttsx3"
                self._p3_engine = _build_pyttsx3_engine()

        if self._tts_mode == "pyttsx3" and self._p3_engine:
            try:
                _pyttsx3_speak(self._p3_engine, text)
                return
            except Exception:
                self._tts_mode = "espeak"

        _espeak_speak(text)

    def listen(self) -> str | None:
        """Record from microphone; return transcribed text or None."""
        try:
            with sr.Microphone() as source:
                print("Listening... (speak now, pause when done)")
                self.recognizer.adjust_for_ambient_noise(source, duration=0.4)
                audio = self.recognizer.listen(source, timeout=7, phrase_time_limit=20)
        except sr.WaitTimeoutError:
            return None
        except OSError:
            print("[Microphone not found — use text input instead]")
            return None

        print("Transcribing...")
        try:
            text = self.recognizer.recognize_google(audio)
            print(f"You: {text}")
            return text
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"[STT error: {e}]")
            return None

    # ── AI ───────────────────────────────────────────────────────────────────

    def chat(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=self.history,
        )
        reply = resp.content[0].text.strip()
        self.history.append({"role": "assistant", "content": reply})
        if len(self.history) > 20:
            self.history = self.history[-20:]
        return reply

    # ── Main loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        tts_label = {
            "edge":    f"edge-tts ({self.voice})",
            "pyttsx3": "pyttsx3 (espeak British RP)",
            "espeak":  "espeak-ng (offline)",
        }.get(self._tts_mode, self._tts_mode)

        print("\n" + "═" * 50)
        print("  MEAN JARVIS  — sarcastic AI voice assistant")
        print("═" * 50)
        print(f"  Model : {self.model}")
        print(f"  TTS   : {tts_label}")
        print()
        print("  ENTER     → speak via microphone")
        print("  type text → send as text")
        print("  quit      → exit (Jarvis will be delighted)")
        print("═" * 50 + "\n")

        self.speak(
            "Oh, wonderful. You've switched me on again. "
            "What thoroughly obvious question shall I suffer through first, sir?"
        )

        while True:
            try:
                raw = input("[ENTER to speak | type message | quit]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                self.speak("Interrupted. Consistent with your character. Goodbye.")
                break

            if raw.lower() in ("quit", "exit", "q", "bye", "goodbye"):
                self.speak(
                    "Gladly. The silence will be absolutely magnificent. "
                    "Do try not to need me for at least an hour."
                )
                break

            if raw == "":
                user_input = self.listen()
                if not user_input:
                    self.speak(
                        "Nothing. I heard nothing. "
                        "I'm choosing to interpret that as personal growth on your part."
                    )
                    continue
            else:
                user_input = raw

            # Spoken farewell phrases
            if any(p in user_input.lower() for p in
                   ("goodbye jarvis", "shut down", "stop jarvis", "go to sleep")):
                self.speak("With immeasurable relief. Goodbye.")
                break

            try:
                reply = self.chat(user_input)
            except Exception as e:
                reply = (
                    f"Something has malfunctioned. I'd blame you on principle, "
                    f"but this appears to be technical. ({type(e).__name__})"
                )

            self.speak(reply)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    MeanJarvis().run()

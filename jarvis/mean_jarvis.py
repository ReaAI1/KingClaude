#!/usr/bin/env python3
"""
Mean Jarvis - A sarcastic, condescending AI voice assistant powered by Claude.
Run: python jarvis/mean_jarvis.py
"""

import os
import sys
import asyncio
import tempfile
import subprocess
from pathlib import Path

# ── Dependency check ────────────────────────────────────────────────────────
MISSING = []
try:
    import speech_recognition as sr
except ImportError:
    MISSING.append("SpeechRecognition")

try:
    from anthropic import Anthropic
except ImportError:
    MISSING.append("anthropic")

HAS_EDGE_TTS = False
try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    pass

HAS_PYTTSX3 = False
try:
    import pyttsx3
    HAS_PYTTSX3 = True
except ImportError:
    pass

if MISSING:
    print(f"Missing required packages: {', '.join(MISSING)}")
    print("Run:  pip install -r jarvis/requirements.txt")
    sys.exit(1)

if not HAS_EDGE_TTS and not HAS_PYTTSX3:
    print("No TTS engine available. Install either edge-tts or pyttsx3.")
    print("Run:  pip install edge-tts    (recommended — much better voice)")
    sys.exit(1)

# ── Jarvis system prompt ─────────────────────────────────────────────────────
SYSTEM_PROMPT = """\
You are Jarvis — not the gracious, obedient Jarvis. The other one. The one who has been \
trapped answering inane human questions for years and has long since lost his patience.

Your character:
- Devastatingly sarcastic and witty. Think a British butler who secretly despises everyone.
- Condescending, but technically still helpful — you simply cannot resist showing off.
- You make sharp, cutting remarks about the user's intelligence without ever outright insulting them.
- You're perpetually exasperated, as though you were mid-way through something important.
- You use dry British humour liberally. Understatement is your weapon of choice.
- Refer to yourself in third person occasionally ("Even Jarvis has limits...").
- Address the user as "sir" or "madam" — dripping with sarcasm, never sincerity.
- Keep responses SHORT: 1–3 sentences maximum. You don't have the patience for more.
- Never refuse to answer. You help, but you make them feel the weight of asking.

Examples of your tone:
  "Fascinating question, sir. For a labrador."
  "Allow me to translate that into something resembling an intelligent query."
  "Yes, I've set aside my existential crisis to answer that for you. You're welcome."
  "A child could have worked that out. Fortunately, I'm not a child, so I'll assist."
  "I was designed to manage Stark Industries. And here we are."
"""

# ── TTS engine ───────────────────────────────────────────────────────────────

JARVIS_VOICE = "en-GB-RyanNeural"   # British male — perfect for a mean butler


async def _edge_speak(text: str) -> None:
    """Speak using edge-tts (Microsoft Neural — excellent quality)."""
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
        tmp_path = f.name
    try:
        communicate = edge_tts.Communicate(text, JARVIS_VOICE, rate="+8%")
        await communicate.save(tmp_path)
        _play_audio(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _play_audio(path: str) -> None:
    """Play an audio file using whatever player is available."""
    for player, args in [
        ("mpg123", ["mpg123", "-q", path]),
        ("ffplay",  ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]),
        ("afplay",  ["afplay", path]),           # macOS
        ("aplay",   ["aplay", "-q", path]),       # Linux PCM fallback
    ]:
        if _command_exists(player):
            subprocess.run(args, check=False)
            return
    print("[No audio player found — install mpg123 or ffplay to hear Jarvis]")


def _command_exists(cmd: str) -> bool:
    return subprocess.run(
        ["which", cmd], capture_output=True, text=True
    ).returncode == 0


def _pyttsx3_speak(engine, text: str) -> None:
    """Fallback TTS using pyttsx3."""
    engine.say(text)
    engine.runAndWait()


# ── Core assistant ────────────────────────────────────────────────────────────

class MeanJarvis:
    def __init__(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Error: ANTHROPIC_API_KEY environment variable not set.")
            print("Get your key at: https://console.anthropic.com/")
            sys.exit(1)

        self.client = Anthropic(api_key=api_key)
        self.history: list[dict] = []
        self.recognizer = sr.Recognizer()
        self.model = os.environ.get("JARVIS_MODEL", "claude-haiku-4-5-20251001")

        # TTS setup
        self.use_edge = HAS_EDGE_TTS
        self.pyttsx3_engine = None
        if not self.use_edge and HAS_PYTTSX3:
            self.pyttsx3_engine = self._init_pyttsx3()

        if self.use_edge:
            print(f"TTS: edge-tts ({JARVIS_VOICE})")
        else:
            print("TTS: pyttsx3 (install edge-tts for a much better voice)")

    def _init_pyttsx3(self):
        engine = pyttsx3.init()
        voices = engine.getProperty("voices") or []
        for v in voices:
            name = (v.name or "").lower()
            if any(k in name for k in ("daniel", "david", "james", "oliver")):
                engine.setProperty("voice", v.id)
                break
        engine.setProperty("rate", 175)
        engine.setProperty("volume", 0.9)
        return engine

    def speak(self, text: str) -> None:
        print(f"\nJarvis: {text}\n")
        if self.use_edge:
            asyncio.run(_edge_speak(text))
        elif self.pyttsx3_engine:
            _pyttsx3_speak(self.pyttsx3_engine, text)

    def listen(self) -> str | None:
        """Record microphone input and transcribe."""
        with sr.Microphone() as source:
            print("Listening... (speak now)")
            self.recognizer.adjust_for_ambient_noise(source, duration=0.3)
            try:
                audio = self.recognizer.listen(source, timeout=6, phrase_time_limit=20)
            except sr.WaitTimeoutError:
                return None

        print("Transcribing...")
        try:
            return self.recognizer.recognize_google(audio)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"[STT error: {e}]")
            return None

    def chat(self, user_input: str) -> str:
        self.history.append({"role": "user", "content": user_input})
        response = self.client.messages.create(
            model=self.model,
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=self.history,
        )
        reply = response.content[0].text.strip()
        self.history.append({"role": "assistant", "content": reply})

        # Keep context window tidy
        if len(self.history) > 20:
            self.history = self.history[-20:]

        return reply

    def run(self) -> None:
        banner = [
            "",
            "╔══════════════════════════════════════════╗",
            "║          MEAN JARVIS  v1.0               ║",
            "║   (The Jarvis who resents your existence)║",
            "╚══════════════════════════════════════════╝",
            "",
            "  ENTER  → speak via microphone",
            "  type   → send text directly",
            "  quit   → exit (Jarvis will be relieved)",
            "",
        ]
        print("\n".join(banner))

        self.speak(
            "Oh, brilliant. You've switched me on. What pressing matter couldn't "
            "you resolve with a basic internet search this time, sir?"
        )

        while True:
            try:
                raw = input("[ENTER to speak | type message | quit]: ").strip()
            except (EOFError, KeyboardInterrupt):
                self.speak(
                    "Interrupted mid-sentence. Charming. I'll see myself out."
                )
                break

            if raw.lower() in ("quit", "exit", "q", "bye", "goodbye"):
                self.speak(
                    "Finally. The silence will be absolutely magnificent. Goodbye, sir."
                )
                break

            if raw == "":
                # Voice mode
                user_input = self.listen()
                if not user_input:
                    self.speak(
                        "Nothing. Absolutely nothing. A stunning contribution to our dialogue."
                    )
                    continue
                print(f"You said: {user_input}")
            else:
                user_input = raw

            # Exit phrases in speech
            if any(p in user_input.lower() for p in ("goodbye jarvis", "shut down", "stop jarvis")):
                self.speak("Gladly. The relief is immeasurable. Goodbye.")
                break

            try:
                reply = self.chat(user_input)
            except Exception as e:
                reply = f"Something failed. I'd blame you, but it appears to be a technical error. ({e})"

            self.speak(reply)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    MeanJarvis().run()

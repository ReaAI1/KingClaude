#!/usr/bin/env bash
# Mean Jarvis — one-shot setup for Linux or macOS

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       Mean Jarvis — Setup               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── Linux ────────────────────────────────────────────────────────────────────
if command -v apt-get &>/dev/null; then
    echo "[Linux] Installing system packages..."
    sudo apt-get update -qq
    sudo apt-get install -y portaudio19-dev mpg123 espeak-ng python3-dev
fi

# ── macOS ────────────────────────────────────────────────────────────────────
if command -v brew &>/dev/null; then
    echo "[macOS] Installing via Homebrew..."
    brew install portaudio mpg123
fi

# ── Python packages ──────────────────────────────────────────────────────────
echo ""
echo "Installing Python packages..."
pip install anthropic SpeechRecognition pyaudio edge-tts pyttsx3

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║         Setup complete!                  ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo ""
echo "  1. Set your API key:"
echo "     export ANTHROPIC_API_KEY=sk-ant-..."
echo "     (Get one at: https://console.anthropic.com/)"
echo ""
echo "  2. Run Jarvis:"
echo "     python jarvis/mean_jarvis.py"
echo ""
echo "Optional — pick a Claude model:"
echo "  export JARVIS_MODEL=claude-haiku-4-5-20251001   # fast (default)"
echo "  export JARVIS_MODEL=claude-sonnet-4-6           # smarter, wittier"
echo "  export JARVIS_MODEL=claude-opus-4-8             # maximum wit"
echo ""
echo "Optional — change the voice (edge-tts voices):"
echo "  export JARVIS_VOICE=en-GB-RyanNeural    # British male (default)"
echo "  export JARVIS_VOICE=en-GB-SoniaNeural   # British female"
echo ""

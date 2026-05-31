#!/usr/bin/env bash
# One-shot setup for Mean Jarvis on Linux/macOS

set -e
echo "=== Mean Jarvis Setup ==="

# System audio deps (Linux)
if command -v apt-get &>/dev/null; then
    echo "[Linux] Installing system audio packages..."
    sudo apt-get install -y portaudio19-dev python3-pyaudio mpg123
elif command -v brew &>/dev/null; then
    echo "[macOS] Installing portaudio via Homebrew..."
    brew install portaudio mpg123
fi

echo "Installing Python packages..."
pip install -r "$(dirname "$0")/requirements.txt"

echo ""
echo "=== Setup complete ==="
echo ""
echo "Set your API key:"
echo "  export ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "Then run Jarvis:"
echo "  python jarvis/mean_jarvis.py"
echo ""
echo "Optional — faster responses (trade wit for speed):"
echo "  export JARVIS_MODEL=claude-haiku-4-5-20251001"
echo "Better responses (trade speed for wit):"
echo "  export JARVIS_MODEL=claude-opus-4-8"

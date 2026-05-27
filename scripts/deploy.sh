#!/usr/bin/env bash
# ── Aurentis AI — Deploy / Update script ─────────────────────────────────
# Run from your LOCAL machine (not the server):
#   bash scripts/deploy.sh user@your-server-ip
set -euo pipefail

SERVER=${1:-""}
APP_DIR=/opt/aurentis-trader
APP_USER=aurentis

if [ -z "$SERVER" ]; then
    echo "Usage: bash scripts/deploy.sh user@server-ip"
    exit 1
fi

echo "=== Deploying to $SERVER ==="

ssh "$SERVER" "
    set -e
    cd $APP_DIR

    echo '-- Pulling latest code --'
    sudo -u $APP_USER git pull

    echo '-- Updating dependencies --'
    sudo -u $APP_USER venv/bin/pip install -r requirements.txt -q

    echo '-- Restarting service --'
    systemctl restart aurentis-trader

    echo '-- Service status --'
    systemctl status aurentis-trader --no-pager -l
"

echo ""
echo "=== Deploy complete! ==="
echo "Dashboard: http://$SERVER"

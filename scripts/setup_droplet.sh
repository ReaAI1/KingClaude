#!/usr/bin/env bash
# ── Aurentis AI — DigitalOcean Droplet Setup ─────────────────────────────
# Run once on a fresh Ubuntu 22.04 droplet as root:
#   bash setup_droplet.sh
set -euo pipefail

APP_DIR=/opt/aurentis-trader
APP_USER=aurentis
REPO_URL=https://github.com/rea-ai-automations/aurentis-trader.git   # update if needed

echo "=== Aurentis AI — Server Setup ==="

# ── System packages ────────────────────────────────────────────────────────
apt-get update -y
apt-get upgrade -y
apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip git curl nginx certbot python3-certbot-nginx \
    build-essential libssl-dev ufw

# ── Firewall ───────────────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable
echo "Firewall configured."

# ── Create app user ────────────────────────────────────────────────────────
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$APP_USER"
    echo "Created user: $APP_USER"
fi

# ── Clone / update repo ────────────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
    echo "Updating existing repo..."
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull
else
    echo "Cloning repo..."
    git clone "$REPO_URL" "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

# ── Python venv ────────────────────────────────────────────────────────────
cd "$APP_DIR"
sudo -u "$APP_USER" python3.11 -m venv venv
sudo -u "$APP_USER" venv/bin/pip install --upgrade pip
sudo -u "$APP_USER" venv/bin/pip install -r requirements.txt
echo "Python environment ready."

# ── .env ──────────────────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo ""
    echo "IMPORTANT: Edit $APP_DIR/.env with your credentials:"
    echo "  nano $APP_DIR/.env"
    echo ""
fi

# ── systemd service ────────────────────────────────────────────────────────
cp "$APP_DIR/systemd/aurentis-trader.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable aurentis-trader
echo "systemd service installed."

# ── Nginx reverse proxy ────────────────────────────────────────────────────
cat > /etc/nginx/sites-available/aurentis << 'NGINX'
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header   Upgrade $http_upgrade;
        proxy_set_header   Connection "upgrade";
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_read_timeout 300s;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/aurentis /etc/nginx/sites-enabled/aurentis
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl restart nginx
echo "Nginx configured."

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Edit your config: nano $APP_DIR/.env"
echo "  2. Start the bot:    systemctl start aurentis-trader"
echo "  3. Check logs:       journalctl -u aurentis-trader -f"
echo "  4. Dashboard:        http://$(curl -s ifconfig.me)"
echo ""

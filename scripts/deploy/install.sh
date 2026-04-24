#!/usr/bin/env bash
# Deploy Governor Chatbot Service to Ubuntu 22.04+ EC2
# Run as: bash install.sh
set -euo pipefail

REPO_URL="https://github.com/TrueSightDAO/governor_chatbot_service.git"
INSTALL_DIR="/opt/governor_chatbot"
SERVICE_FILE="/etc/systemd/system/governor-chatbot.service"

echo "=== Governor Chatbot Deploy ==="

# 1. System deps
echo "[1/6] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq git python3 python3-venv python3-pip

# 2. Clone repo
echo "[2/6] Cloning repo..."
if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git pull origin main
else
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown ubuntu:ubuntu "$INSTALL_DIR"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# 3. Python venv + deps
echo "[3/6] Creating venv and installing deps..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

# 4. Environment
echo "[4/6] Environment setup..."
if [ ! -f ".env" ]; then
    echo "WARNING: .env not found. Copy .env from your local machine to $INSTALL_DIR/.env"
    echo "  scp .env ubuntu@<EC2_IP>:/opt/governor_chatbot/.env"
    exit 1
fi

# 5. Systemd service
echo "[5/6] Installing systemd service..."
sudo cp scripts/deploy/governor-chatbot.service "$SERVICE_FILE"
sudo systemctl daemon-reload
sudo systemctl enable governor-chatbot
sudo systemctl restart governor-chatbot

# 6. Health check
echo "[6/6] Health check..."
sleep 2
if curl -sf http://127.0.0.1:8000/health > /dev/null; then
    echo "✅ Governor Chatbot is running on http://127.0.0.1:8000"
else
    echo "⚠️ Service may still be starting. Check: sudo journalctl -u governor-chatbot -f"
fi

echo ""
echo "=== Next steps ==="
echo "1. Configure nginx reverse proxy (see scripts/deploy/nginx-chatbot.conf)"
echo "2. Add Route 53 A record: chatbot.truesight.me → <this server IP>"
echo "3. Update DApp chat.html API_BASE_URL to https://chatbot.truesight.me"

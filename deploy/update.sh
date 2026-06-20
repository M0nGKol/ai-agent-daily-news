#!/usr/bin/env bash
# update.sh — pull latest code and restart the bot on the server
#
# Usage (run as your normal user, NOT root):
#   bash /opt/ai-agents-daily-news/deploy/update.sh

set -euo pipefail

APP_DIR="/opt/ai-agents-daily-news"
RUN_AS="${USER}"
BOT_SERVICE="ai-digest-bot@${RUN_AS}.service"

cd "$APP_DIR"

echo "==> Pulling latest code..."
git pull

echo "==> Updating Python dependencies..."
.venv/bin/pip install --quiet -r requirements.txt

echo "==> Restarting command bot..."
sudo systemctl restart "$BOT_SERVICE"

echo ""
echo "✓ Done. Bot is running with the latest code."
echo "  Logs: journalctl -u $BOT_SERVICE -f"

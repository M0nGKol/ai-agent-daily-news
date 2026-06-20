#!/usr/bin/env bash
# install.sh — deploy ai-agents-daily-news to a Ubuntu/Debian server
#
# Usage (run as root or with sudo):
#   sudo bash deploy/install.sh [USERNAME]
#
# USERNAME defaults to the current non-root user, or "ubuntu" if run as root.
# The script installs the app under /opt/ai-agents-daily-news and configures
# a systemd timer to run the digest daily at 07:00 ICT (00:00 UTC).

set -euo pipefail

# ── Config ────────────────────────────────────────────────────────────────────
APP_DIR="/opt/ai-agents-daily-news"
SERVICE_NAME="ai-digest"

if [[ "${1-}" != "" ]]; then
  RUN_AS="$1"
elif [[ "$EUID" -ne 0 ]]; then
  RUN_AS="$USER"
else
  RUN_AS="${SUDO_USER:-ubuntu}"
fi

# ── Checks ────────────────────────────────────────────────────────────────────
if [[ "$EUID" -ne 0 ]]; then
  echo "ERROR: run this script with sudo." >&2
  exit 1
fi

if ! id "$RUN_AS" &>/dev/null; then
  echo "ERROR: user '$RUN_AS' does not exist." >&2
  exit 1
fi

echo "==> Installing as user: $RUN_AS"
echo "==> App directory:      $APP_DIR"

# ── System dependencies ───────────────────────────────────────────────────────
echo "==> Installing system packages..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git

# ── Copy app files ────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_DIR="$(dirname "$SCRIPT_DIR")"

echo "==> Syncing app files to $APP_DIR..."
rsync -a --delete \
  --exclude='.git' \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.env' \
  --exclude='state' \
  "$SRC_DIR/" "$APP_DIR/"

# ── .env file ─────────────────────────────────────────────────────────────────
if [[ -f "$APP_DIR/.env" ]]; then
  echo "==> .env already exists at $APP_DIR/.env — leaving it untouched."
elif [[ -f "$SRC_DIR/.env" ]]; then
  echo "==> Copying .env..."
  cp "$SRC_DIR/.env" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
else
  echo ""
  echo "WARNING: No .env found. Copy your .env to $APP_DIR/.env before running."
  echo "  sudo cp /path/to/your/.env $APP_DIR/.env"
  echo "  sudo chmod 600 $APP_DIR/.env"
  echo "  sudo chown $RUN_AS:$RUN_AS $APP_DIR/.env"
  echo ""
fi

# ── State directory ───────────────────────────────────────────────────────────
mkdir -p "$APP_DIR/state"

# ── Virtual environment ───────────────────────────────────────────────────────
echo "==> Setting up Python virtual environment..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ── Ownership ─────────────────────────────────────────────────────────────────
chown -R "$RUN_AS:$RUN_AS" "$APP_DIR"

# ── systemd units ─────────────────────────────────────────────────────────────
echo "==> Installing systemd units..."

# The service uses the instance specifier (%i) for the username.
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}@.service"
TIMER_FILE="/etc/systemd/system/${SERVICE_NAME}@${RUN_AS}.timer"

# Patch WorkingDirectory and venv path into service file
sed "s|/opt/ai-agents-daily-news|$APP_DIR|g" \
  "$APP_DIR/deploy/ai-digest.service" > "$SERVICE_FILE"

# Patch the Requires= line in the timer to match the actual service instance
sed "s|%i|$RUN_AS|g" \
  "$APP_DIR/deploy/ai-digest.timer" > "$TIMER_FILE"

chmod 644 "$SERVICE_FILE" "$TIMER_FILE"

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}@${RUN_AS}.timer"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "✓ Installation complete."
echo ""
echo "Useful commands:"
echo "  Check timer status:    systemctl status ${SERVICE_NAME}@${RUN_AS}.timer"
echo "  Run digest now:        systemctl start ${SERVICE_NAME}@${RUN_AS}.service"
echo "  View logs:             journalctl -u ${SERVICE_NAME}@${RUN_AS}.service -f"
echo "  Next scheduled run:    systemctl list-timers ${SERVICE_NAME}*"

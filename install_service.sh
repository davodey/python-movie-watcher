#!/bin/bash
# Install Jellyfin Auto-Organizer as a systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="jellyfin-organizer"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"
PYTHON_BIN="$(which python3)"

# Must run as root
if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (use sudo)"
    exit 1
fi

# Get the user who invoked sudo
REAL_USER="${SUDO_USER:-$USER}"

echo "============================================"
echo "  Installing Jellyfin Auto-Organizer Service"
echo "============================================"
echo

# Verify config exists
if [ ! -f "$SCRIPT_DIR/config.json" ]; then
    echo "ERROR: config.json not found. Run setup.sh first."
    exit 1
fi

# Create systemd service file
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Jellyfin Auto-Organizer
Documentation=https://github.com/davodey/python-movie-watcher
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_BIN -m jellyfin_organizer.main -c $SCRIPT_DIR/config.json
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/log /var/lib/jellyfin_organizer

[Install]
WantedBy=multi-user.target
EOF

echo "Service file created: $SERVICE_FILE"

# Create log and data directories
mkdir -p /var/lib/jellyfin_organizer
touch /var/log/jellyfin_organizer.log
chown "$REAL_USER:$REAL_USER" /var/log/jellyfin_organizer.log
chown -R "$REAL_USER:$REAL_USER" /var/lib/jellyfin_organizer

# Add ReadWritePaths for watch and destination dirs from config
WATCH_DIR=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.json'))['watch_directory'])" 2>/dev/null || echo "")
DEST_DIR=$(python3 -c "import json; print(json.load(open('$SCRIPT_DIR/config.json'))['destination_directory'])" 2>/dev/null || echo "")

if [ -n "$WATCH_DIR" ] || [ -n "$DEST_DIR" ]; then
    # Append media paths to ReadWritePaths
    sed -i "s|ReadWritePaths=/var/log /var/lib/jellyfin_organizer|ReadWritePaths=/var/log /var/lib/jellyfin_organizer $WATCH_DIR $DEST_DIR|" "$SERVICE_FILE"
fi

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

echo
echo "============================================"
echo "  Service Installed Successfully!"
echo "============================================"
echo
echo "Commands:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo "  Disable: sudo systemctl disable $SERVICE_NAME"
echo

#!/bin/bash
# Install Media Sanitizer with n8n AI Enrichment
#
# This script:
# 1. Installs Python dependencies
# 2. Creates necessary directories
# 3. Sets up configuration file
# 4. Optionally installs as systemd service

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/sanitizer_config.json"
CONFIG_EXAMPLE="$SCRIPT_DIR/sanitizer_config.json.example"
SERVICE_NAME="media-sanitizer"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=============================================="
echo "  Media Sanitizer Installation"
echo "  Complete TMDb Metadata + n8n AI Enrichment"
echo "=============================================="
echo

# Check Python 3.10+
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 10 ]); then
    echo -e "${RED}ERROR: Python 3.10+ is required. Found: Python $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}[OK]${NC} Python $PYTHON_VERSION found"

# Install dependencies
echo
echo "Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt" --quiet
echo -e "${GREEN}[OK]${NC} Dependencies installed"

# Create default config if it doesn't exist
if [ ! -f "$CONFIG_FILE" ] || grep -q "YOUR_TMDB_API_KEY" "$CONFIG_FILE"; then
    echo
    echo -e "${YELLOW}Configuration needed:${NC}"
    echo

    # Ask for TMDb API key
    read -p "Enter your TMDb API key (get one at https://www.themoviedb.org/settings/api): " TMDB_KEY

    if [ -z "$TMDB_KEY" ]; then
        echo -e "${RED}ERROR: TMDb API key is required${NC}"
        exit 1
    fi

    # Ask for n8n webhook URL (optional)
    echo
    read -p "Enter n8n webhook URL (leave blank to skip AI enrichment): " N8N_URL

    if [ -z "$N8N_URL" ]; then
        N8N_URL="null"
    else
        N8N_URL="\"$N8N_URL\""
    fi

    # Ask for directories
    echo
    read -p "Movies watch directory [/mnt/media/torrents/complete/movies]: " MOVIES_WATCH
    MOVIES_WATCH="${MOVIES_WATCH:-/mnt/media/torrents/complete/movies}"

    read -p "Movies output directory [/mnt/media/sanatize/movies]: " MOVIES_OUTPUT
    MOVIES_OUTPUT="${MOVIES_OUTPUT:-/mnt/media/sanatize/movies}"

    read -p "TV watch directory [/mnt/media/torrents/complete/tv]: " TV_WATCH
    TV_WATCH="${TV_WATCH:-/mnt/media/torrents/complete/tv}"

    read -p "TV output directory [/mnt/media/sanatize/tv]: " TV_OUTPUT
    TV_OUTPUT="${TV_OUTPUT:-/mnt/media/sanatize/tv}"

    # Create config file
    cat > "$CONFIG_FILE" <<EOF
{
  "tmdb_api_key": "$TMDB_KEY",
  "n8n_webhook_url": $N8N_URL,

  "watch_folders": {
    "movies": "$MOVIES_WATCH",
    "tv": "$TV_WATCH"
  },

  "output_folders": {
    "movies": "$MOVIES_OUTPUT",
    "tv": "$TV_OUTPUT"
  },

  "watch_interval": 60,
  "database_path": "$SCRIPT_DIR/sanitizer.db",
  "log_file": "$SCRIPT_DIR/sanitizer.log",

  "tmdb_options": {
    "include_adult": false,
    "language": "en-US",
    "image_base_url": "https://image.tmdb.org/t/p/original"
  },

  "n8n_options": {
    "timeout": 30,
    "retry_count": 3
  },

  "file_extensions": [".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".mov"],
  "subtitle_extensions": [".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx"],
  "min_file_size_mb": 100,
  "settle_time": 30
}
EOF

    echo -e "${GREEN}[OK]${NC} Configuration saved to $CONFIG_FILE"
fi

# Create directories
echo
echo "Creating directories..."
MOVIES_WATCH=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('watch_folders', {}).get('movies', ''))" 2>/dev/null || echo "")
MOVIES_OUTPUT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('output_folders', {}).get('movies', ''))" 2>/dev/null || echo "")
TV_WATCH=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('watch_folders', {}).get('tv', ''))" 2>/dev/null || echo "")
TV_OUTPUT=$(python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('output_folders', {}).get('tv', ''))" 2>/dev/null || echo "")

for DIR in "$MOVIES_WATCH" "$MOVIES_OUTPUT" "$TV_WATCH" "$TV_OUTPUT"; do
    if [ -n "$DIR" ] && [ ! -d "$DIR" ]; then
        mkdir -p "$DIR" 2>/dev/null && echo "  Created: $DIR" || echo "  Skipped (permission denied): $DIR"
    fi
done

echo -e "${GREEN}[OK]${NC} Directories ready"

# Ask about systemd service
echo
read -p "Install as systemd service? (y/n) [n]: " INSTALL_SERVICE
if [[ "$INSTALL_SERVICE" =~ ^[Yy]$ ]]; then
    if [ "$EUID" -ne 0 ]; then
        echo -e "${YELLOW}Run this script with sudo to install the service:${NC}"
        echo "  sudo $0"
    else
        # Create systemd service
        REAL_USER="${SUDO_USER:-$USER}"
        PYTHON_BIN="$(which python3)"
        SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

        cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Media Sanitizer with TMDb + n8n AI Enrichment
Documentation=https://github.com/davodey/python-movie-watcher
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_BIN -m jellyfin_organizer.sanitizer_main -c $CONFIG_FILE
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

# Security
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=$SCRIPT_DIR $MOVIES_WATCH $MOVIES_OUTPUT $TV_WATCH $TV_OUTPUT /var/log

[Install]
WantedBy=multi-user.target
EOF

        systemctl daemon-reload
        systemctl enable "$SERVICE_NAME"

        echo -e "${GREEN}[OK]${NC} Service installed: $SERVICE_NAME"
        echo
        echo "Service commands:"
        echo "  Start:   sudo systemctl start $SERVICE_NAME"
        echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
        echo "  Status:  sudo systemctl status $SERVICE_NAME"
        echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
    fi
fi

echo
echo "=============================================="
echo "  Installation Complete!"
echo "=============================================="
echo
echo "To run manually:"
echo "  python3 -m jellyfin_organizer.sanitizer_main -c $CONFIG_FILE"
echo
echo "To process existing files:"
echo "  python3 -m jellyfin_organizer.sanitizer_main -c $CONFIG_FILE --scan-existing"
echo
echo "To see statistics:"
echo "  python3 -m jellyfin_organizer.sanitizer_main -c $CONFIG_FILE --stats"
echo

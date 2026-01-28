#!/bin/bash
# Jellyfin Auto-Organizer Setup Script
# Creates config file and installs dependencies

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"

echo "============================================"
echo "  Jellyfin Auto-Organizer - Setup"
echo "============================================"
echo

# Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 is required but not installed."
    echo "Install with: sudo apt install python3 python3-pip"
    exit 1
fi

echo "Python 3 found: $(python3 --version)"
echo

# Install dependencies
echo "Installing Python dependencies..."
pip3 install -r "$SCRIPT_DIR/requirements.txt"
echo

# Create config file if it doesn't exist
if [ -f "$CONFIG_FILE" ]; then
    echo "Config file already exists: $CONFIG_FILE"
    echo "To reconfigure, edit the file directly or delete it and re-run setup."
    echo
else
    echo "--- Configuration ---"
    echo

    # TMDb API Key
    echo "You need a TMDb API key (free)."
    echo "Get one at: https://www.themoviedb.org/settings/api"
    echo
    read -rp "Enter your TMDb API key: " TMDB_KEY

    if [ -z "$TMDB_KEY" ]; then
        echo "ERROR: TMDb API key is required."
        exit 1
    fi

    # Watch directory
    read -rp "Watch directory [/media/david/MEDIA/torrents/complete/movies]: " WATCH_DIR
    WATCH_DIR="${WATCH_DIR:-/media/david/MEDIA/torrents/complete/movies}"

    # Destination directory
    read -rp "Destination directory [/media/david/MEDIA/media/movies]: " DEST_DIR
    DEST_DIR="${DEST_DIR:-/media/david/MEDIA/media/movies}"

    # Write config
    cat > "$CONFIG_FILE" <<EOF
{
    "tmdb_api_key": "$TMDB_KEY",
    "watch_directory": "$WATCH_DIR",
    "destination_directory": "$DEST_DIR",
    "settle_time": 30,
    "min_file_size_mb": 100,
    "scan_interval": 60,
    "log_file": "/var/log/jellyfin_organizer.log",
    "database_file": "/var/lib/jellyfin_organizer/processed.db",
    "video_extensions": [".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts"],
    "subtitle_extensions": [".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx"]
}
EOF

    echo
    echo "Config written to: $CONFIG_FILE"
fi

# Create required directories
echo
echo "Creating required directories..."
sudo mkdir -p /var/log
sudo mkdir -p /var/lib/jellyfin_organizer
sudo touch /var/log/jellyfin_organizer.log
sudo chown "$USER:$USER" /var/log/jellyfin_organizer.log
sudo chown -R "$USER:$USER" /var/lib/jellyfin_organizer

echo
echo "============================================"
echo "  Setup Complete!"
echo "============================================"
echo
echo "Next steps:"
echo "  1. Review config: $CONFIG_FILE"
echo "  2. Install as service: sudo ./install_service.sh"
echo "  3. Or run manually: python3 -m jellyfin_organizer.main"
echo

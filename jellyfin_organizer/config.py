"""Configuration management for Jellyfin Auto-Organizer."""

import json
import os
import sys

DEFAULT_CONFIG = {
    "tmdb_api_key": "",
    "watch_directory": "/media/david/MEDIA/torrents/complete/movies",
    "destination_directory": "/media/david/MEDIA/media/movies",
    "settle_time": 30,
    "min_file_size_mb": 100,
    "scan_interval": 60,
    "log_file": "/var/log/jellyfin_organizer.log",
    "database_file": "/var/lib/jellyfin_organizer/processed.db",
    "video_extensions": [".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts"],
    "subtitle_extensions": [".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx"],
}

CONFIG_SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json"),
    os.path.expanduser("~/.config/jellyfin_organizer/config.json"),
    "/etc/jellyfin_organizer/config.json",
]


def find_config_file():
    """Find the config file from known search paths."""
    for path in CONFIG_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return None


def load_config(config_path=None):
    """Load configuration from JSON file, merged with defaults.

    Args:
        config_path: Optional explicit path to config file.

    Returns:
        dict: Merged configuration.

    Raises:
        SystemExit: If no config file found or TMDb API key missing.
    """
    config = dict(DEFAULT_CONFIG)

    if config_path is None:
        config_path = find_config_file()

    if config_path and os.path.isfile(config_path):
        with open(config_path, "r") as f:
            user_config = json.load(f)
        config.update(user_config)
    else:
        print(f"ERROR: No config file found. Searched: {CONFIG_SEARCH_PATHS}", file=sys.stderr)
        print("Run setup.sh to create a configuration file.", file=sys.stderr)
        sys.exit(1)

    if not config.get("tmdb_api_key"):
        print("ERROR: TMDb API key not set in config file.", file=sys.stderr)
        print("Get a free key at https://www.themoviedb.org/settings/api", file=sys.stderr)
        sys.exit(1)

    return config

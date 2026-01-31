"""Entry point for the Media Sanitizer service."""

import argparse
import json
import logging
import os
import signal
import sys

from .sanitizer import MediaSanitizer


# Default configuration for the sanitizer
DEFAULT_SANITIZER_CONFIG = {
    "watch_directories": [
        {
            "source": "/mnt/media/torrents/complete/tv",
            "destination": "/mnt/media/sanatize/tv",
            "media_type": "tv"
        },
        {
            "source": "/mnt/media/torrents/complete/movies",
            "destination": "/mnt/media/sanatize/movies",
            "media_type": "movies"
        }
    ],
    "settle_time": 30,
    "min_file_size_mb": 100,
    "scan_interval": 60,
    "log_file": "/var/log/media_sanitizer.log",
    "video_extensions": [".mkv", ".mp4", ".avi", ".m4v", ".wmv", ".flv", ".mov", ".ts"],
}

CONFIG_SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sanitizer_config.json"),
    os.path.expanduser("~/.config/media_sanitizer/config.json"),
    "/etc/media_sanitizer/config.json",
]


def find_config_file():
    """Find the config file from known search paths."""
    for path in CONFIG_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    return None


def load_config(config_path=None):
    """Load configuration from JSON file, merged with defaults."""
    config = dict(DEFAULT_SANITIZER_CONFIG)

    if config_path is None:
        config_path = find_config_file()

    if config_path and os.path.isfile(config_path):
        with open(config_path, "r") as f:
            user_config = json.load(f)
        config.update(user_config)
        print(f"Loaded config from: {config_path}")
    else:
        print("No config file found, using defaults.")
        print(f"Searched: {CONFIG_SEARCH_PATHS}")

    return config


def setup_logging(log_file):
    """Configure logging to both file and console."""
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
    except PermissionError:
        file_handler = None
        print(f"Warning: Cannot write to log file {log_file}, using console only")

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    if file_handler:
        root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def main():
    """CLI entry point for the Media Sanitizer."""
    parser = argparse.ArgumentParser(
        description="Media Sanitizer - Watch directories and sanitize media filenames",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to sanitizer_config.json file",
    )
    parser.add_argument(
        "--scan-existing",
        action="store_true",
        help="Process all existing files in watch directories on startup",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup logging
    setup_logging(config.get("log_file", "/var/log/media_sanitizer.log"))

    logger = logging.getLogger(__name__)

    # Create the sanitizer service
    service = MediaSanitizer(config)

    # Handle signals for graceful shutdown
    def signal_handler(signum, frame):
        service.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Process existing files if requested
    if args.scan_existing:
        logger.info("Processing existing files in watch directories...")
        service.process_existing()

    # Start the service
    service.start()


if __name__ == "__main__":
    main()

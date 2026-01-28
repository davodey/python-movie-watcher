"""Main entry point for the Jellyfin Auto-Organizer service."""

import argparse
import logging
import os
import signal
import sys
import time

from .config import load_config
from .database import ProcessedDatabase
from .organizer import MovieOrganizer
from .parser import parse_movie_filename
from .tmdb import TMDbClient
from .watcher import MovieWatcher


def setup_logging(log_file):
    """Configure logging to both file and console.

    Args:
        log_file: Path to the log file.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


logger = logging.getLogger(__name__)


class JellyfinOrganizer:
    """Main service class that orchestrates the auto-organization pipeline."""

    def __init__(self, config):
        self.config = config
        self.running = False

        # Initialize components
        self.tmdb = TMDbClient(config["tmdb_api_key"])
        self.db = ProcessedDatabase(config["database_file"])
        self.watcher = MovieWatcher(
            watch_dir=config["watch_directory"],
            video_extensions=config["video_extensions"],
            min_size_mb=config["min_file_size_mb"],
            settle_time=config["settle_time"],
        )
        self.organizer = MovieOrganizer(
            destination_dir=config["destination_directory"],
            subtitle_extensions=config["subtitle_extensions"],
        )

    def start(self):
        """Start the organizer service main loop."""
        self.running = True
        logger.info("=" * 60)
        logger.info("Jellyfin Auto-Organizer starting")
        logger.info("Watch directory: %s", self.config["watch_directory"])
        logger.info("Destination: %s", self.config["destination_directory"])
        logger.info("Scan interval: %d seconds", self.config["scan_interval"])
        logger.info("=" * 60)

        # Validate directories exist
        if not os.path.isdir(self.config["watch_directory"]):
            logger.error("Watch directory does not exist: %s", self.config["watch_directory"])
            logger.info("Creating watch directory...")
            os.makedirs(self.config["watch_directory"], exist_ok=True)

        os.makedirs(self.config["destination_directory"], exist_ok=True)

        # Initial scan to populate known entries (don't process existing files)
        logger.info("Performing initial scan to detect existing files...")
        existing = self.watcher.scan()
        logger.info("Found %d existing entries (will not reprocess)", len(existing))

        while self.running:
            try:
                self._scan_and_process()
            except Exception:
                logger.exception("Error during scan cycle")

            # Sleep in small increments so we can respond to stop signals
            for _ in range(self.config["scan_interval"]):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Jellyfin Auto-Organizer stopped")

    def stop(self):
        """Stop the organizer service."""
        logger.info("Stop signal received")
        self.running = False

    def _scan_and_process(self):
        """Run one scan cycle: detect new entries and process them."""
        new_entries = self.watcher.scan()

        for entry_path in new_entries:
            if not self.running:
                break
            self._process_entry(entry_path)

    def _process_entry(self, entry_path):
        """Process a single new file or folder.

        Args:
            entry_path: Path to the new entry in the watch directory.
        """
        entry_name = os.path.basename(entry_path)
        logger.info("-" * 50)
        logger.info("New entry detected: %s", entry_name)

        # Check if already processed
        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping: %s", entry_name)
            return

        # Validate entry and find main video file
        video_path = self.watcher.validate_entry(entry_path)
        if not video_path:
            logger.info("No valid video file found, skipping: %s", entry_name)
            return

        # Wait for file to stabilize
        if not self.watcher.wait_for_stable(video_path):
            logger.warning("File not stable, skipping: %s", entry_name)
            return

        # Parse filename
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_path)
        parsed = parse_movie_filename(parse_name)
        logger.info("Parsed: title='%s', year=%s", parsed["title"], parsed["year"])

        # Search TMDb
        logger.info("Searching TMDb for: %s (%s)", parsed["title"], parsed["year"])
        movie_data = self.tmdb.get_full_movie_info(parsed["title"], parsed["year"])

        if not movie_data:
            logger.warning("No TMDb match found for: %s", parsed["title"])
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("TMDb match: %s (%s) [ID: %s]",
                     movie_data["title"], movie_data["year"], movie_data["tmdb_id"])

        # Organize the movie
        dest_folder = self.organizer.organize(
            video_path=video_path,
            source_entry=entry_path,
            movie_data=movie_data,
            parsed_info=parsed,
        )

        if dest_folder:
            self.db.mark_processed(
                source_path=entry_path,
                dest_path=dest_folder,
                title=movie_data["title"],
                year=movie_data.get("year"),
                tmdb_id=movie_data.get("tmdb_id"),
                status="success",
            )
            logger.info("SUCCESS: %s -> %s", entry_name, dest_folder)
        else:
            self.db.mark_processed(entry_path, status="failed")
            logger.error("FAILED: %s", entry_name)

    def process_single(self, path):
        """Process a single file or folder on-demand (non-service mode).

        Args:
            path: Path to process.
        """
        if not os.path.exists(path):
            logger.error("Path does not exist: %s", path)
            return False

        self._process_entry(os.path.abspath(path))
        return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Jellyfin Auto-Organizer - Automatically organize movie downloads",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to config.json file",
    )
    parser.add_argument(
        "--process",
        help="Process a single file/folder and exit (non-service mode)",
    )
    parser.add_argument(
        "--scan-existing",
        action="store_true",
        help="Process all existing files in watch directory on startup",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Clear failed entries from database so they are retried",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup logging
    setup_logging(config["log_file"])

    # Create the organizer
    service = JellyfinOrganizer(config)

    # Handle signals for graceful shutdown
    def signal_handler(signum, frame):
        service.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    if args.retry_failed:
        cleared = service.db.clear_failed()
        logger.info("Cleared %d failed entries for retry", cleared)

    if args.process:
        # Single file mode
        service.process_single(args.process)
    else:
        # Service mode
        if args.scan_existing:
            logger.info("Processing existing files in watch directory...")
            if os.path.isdir(config["watch_directory"]):
                for entry in sorted(os.listdir(config["watch_directory"])):
                    entry_path = os.path.join(config["watch_directory"], entry)
                    service._process_entry(entry_path)

        service.start()


if __name__ == "__main__":
    main()

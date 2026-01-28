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
from .parser import parse_movie_filename, parse_tv_filename
from .tmdb import TMDbClient
from .tv_organizer import TVOrganizer
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

        # Initialize shared components
        self.tmdb = TMDbClient(config["tmdb_api_key"])
        self.db = ProcessedDatabase(config["database_file"])

        # Movie components
        self.movie_watcher = MovieWatcher(
            watch_dir=config["watch_directory"],
            video_extensions=config["video_extensions"],
            min_size_mb=config["min_file_size_mb"],
            settle_time=config["settle_time"],
        )
        self.movie_organizer = MovieOrganizer(
            destination_dir=config["destination_directory"],
            subtitle_extensions=config["subtitle_extensions"],
        )

        # TV show components (if TV directories configured)
        self.tv_watcher = None
        self.tv_organizer = None
        if config.get("tv_watch_directory") and config.get("tv_destination_directory"):
            self.tv_watcher = MovieWatcher(
                watch_dir=config["tv_watch_directory"],
                video_extensions=config["video_extensions"],
                min_size_mb=config["min_file_size_mb"],
                settle_time=config["settle_time"],
            )
            self.tv_organizer = TVOrganizer(
                destination_dir=config["tv_destination_directory"],
                subtitle_extensions=config["subtitle_extensions"],
            )

    def start(self):
        """Start the organizer service main loop."""
        self.running = True
        logger.info("=" * 60)
        logger.info("Jellyfin Auto-Organizer starting")
        logger.info("Movie watch: %s", self.config["watch_directory"])
        logger.info("Movie dest:  %s", self.config["destination_directory"])
        if self.tv_watcher:
            logger.info("TV watch:    %s", self.config["tv_watch_directory"])
            logger.info("TV dest:     %s", self.config["tv_destination_directory"])
        logger.info("Scan interval: %d seconds", self.config["scan_interval"])
        logger.info("=" * 60)

        # Validate and create directories
        self._ensure_directories()

        # Initial scan to populate known entries
        logger.info("Performing initial scan to detect existing files...")
        movie_existing = self.movie_watcher.scan()
        logger.info("Found %d existing movie entries", len(movie_existing))

        if self.tv_watcher:
            tv_existing = self.tv_watcher.scan()
            logger.info("Found %d existing TV entries", len(tv_existing))

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

    def _ensure_directories(self):
        """Create watch and destination directories if they don't exist."""
        for key in ["watch_directory", "destination_directory"]:
            path = self.config.get(key)
            if path and not os.path.isdir(path):
                logger.info("Creating directory: %s", path)
                os.makedirs(path, exist_ok=True)

        if self.tv_watcher:
            for key in ["tv_watch_directory", "tv_destination_directory"]:
                path = self.config.get(key)
                if path and not os.path.isdir(path):
                    logger.info("Creating directory: %s", path)
                    os.makedirs(path, exist_ok=True)

    def stop(self):
        """Stop the organizer service."""
        logger.info("Stop signal received")
        self.running = False

    def _scan_and_process(self):
        """Run one scan cycle: detect new entries and process them."""
        # Process movies
        for entry_path in self.movie_watcher.scan():
            if not self.running:
                break
            self._process_movie_entry(entry_path)

        # Process TV shows
        if self.tv_watcher:
            for entry_path in self.tv_watcher.scan():
                if not self.running:
                    break
                self._process_tv_entry(entry_path)

    def _process_movie_entry(self, entry_path):
        """Process a single movie file or folder.

        Args:
            entry_path: Path to the entry in the movie watch directory.
        """
        entry_name = os.path.basename(entry_path)
        logger.info("-" * 50)
        logger.info("[MOVIE] New entry: %s", entry_name)

        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping: %s", entry_name)
            return

        video_path = self.movie_watcher.validate_entry(entry_path)
        if not video_path:
            logger.info("No valid video file found, skipping: %s", entry_name)
            return

        if not self.movie_watcher.wait_for_stable(video_path):
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

        # Organize
        dest_folder = self.movie_organizer.organize(
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

    def _process_tv_entry(self, entry_path):
        """Process a TV show entry (could be single episode or season folder).

        Args:
            entry_path: Path to the entry in the TV watch directory.
        """
        entry_name = os.path.basename(entry_path)
        logger.info("-" * 50)
        logger.info("[TV] New entry: %s", entry_name)

        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping: %s", entry_name)
            return

        # Find all video files in this entry
        video_files = self._find_tv_videos(entry_path)
        if not video_files:
            logger.info("No valid video files found, skipping: %s", entry_name)
            return

        # Try to identify the show from the entry name or first video
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_files[0])
        parsed = parse_tv_filename(parse_name)

        if not parsed:
            logger.warning("Could not parse as TV show: %s", parse_name)
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("Parsed: show='%s' S%02d year=%s",
                    parsed["show"], parsed["season"], parsed["year"])

        # Search TMDb for the show
        logger.info("Searching TMDb for TV show: %s", parsed["show"])
        show_data = self.tmdb.get_full_tv_info(parsed["show"], parsed["year"])

        if not show_data:
            logger.warning("No TMDb TV match found for: %s", parsed["show"])
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("TMDb match: %s (%s) [ID: %s]",
                    show_data["title"], show_data["year"], show_data["tmdb_id"])

        # Process each video file
        success_count = 0
        for video_path in video_files:
            if not self.running:
                break

            if not self.tv_watcher.wait_for_stable(video_path):
                logger.warning("File not stable, skipping: %s", os.path.basename(video_path))
                continue

            # Parse this specific episode
            ep_parsed = parse_tv_filename(os.path.basename(video_path))
            if not ep_parsed:
                ep_parsed = parsed  # Fall back to folder-level parsing

            # Get episode metadata
            episode_data = None
            if ep_parsed.get("episode"):
                episode_data = self.tmdb.get_full_episode_info(
                    show_data["tmdb_id"],
                    ep_parsed["season"],
                    ep_parsed["episode"],
                )

            # Organize this episode
            dest_path = self.tv_organizer.organize_episode(
                video_path=video_path,
                source_entry=entry_path,
                show_data=show_data,
                episode_data=episode_data,
                parsed_info=ep_parsed,
            )

            if dest_path:
                success_count += 1
                logger.info("Episode organized: %s", os.path.basename(dest_path))

        # Clean up source folder if all episodes processed
        if success_count > 0:
            if os.path.isdir(entry_path):
                self.tv_organizer.cleanup_source(entry_path)

            self.db.mark_processed(
                source_path=entry_path,
                dest_path=self.config["tv_destination_directory"],
                title=show_data["title"],
                year=show_data.get("year"),
                tmdb_id=show_data.get("tmdb_id"),
                status="success",
            )
            logger.info("SUCCESS: %s (%d episodes)", entry_name, success_count)
        else:
            self.db.mark_processed(entry_path, status="failed")
            logger.error("FAILED: %s", entry_name)

    def _find_tv_videos(self, entry_path):
        """Find all video files in a TV entry.

        Args:
            entry_path: Path to file or directory.

        Returns:
            list: Sorted list of video file paths.
        """
        videos = []
        video_exts = set(self.config["video_extensions"])
        min_size = self.config["min_file_size_mb"] * 1024 * 1024

        if os.path.isfile(entry_path):
            _, ext = os.path.splitext(entry_path)
            if ext.lower() in video_exts and os.path.getsize(entry_path) >= min_size:
                videos.append(entry_path)
        elif os.path.isdir(entry_path):
            for root, _, files in os.walk(entry_path):
                for f in files:
                    fpath = os.path.join(root, f)
                    _, ext = os.path.splitext(f)
                    if ext.lower() in video_exts:
                        try:
                            if os.path.getsize(fpath) >= min_size:
                                videos.append(fpath)
                        except OSError:
                            pass

        return sorted(videos)

    def process_single(self, path, media_type="auto"):
        """Process a single file or folder on-demand.

        Args:
            path: Path to process.
            media_type: 'movie', 'tv', or 'auto' to detect.
        """
        if not os.path.exists(path):
            logger.error("Path does not exist: %s", path)
            return False

        path = os.path.abspath(path)

        if media_type == "auto":
            # Try to detect based on filename
            name = os.path.basename(path)
            if parse_tv_filename(name):
                media_type = "tv"
            else:
                media_type = "movie"

        if media_type == "tv" and self.tv_organizer:
            self._process_tv_entry(path)
        else:
            self._process_movie_entry(path)

        return True


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Jellyfin Auto-Organizer - Organize movie and TV downloads",
    )
    parser.add_argument(
        "-c", "--config",
        help="Path to config.json file",
    )
    parser.add_argument(
        "--process",
        help="Process a single file/folder and exit",
    )
    parser.add_argument(
        "--type",
        choices=["auto", "movie", "tv"],
        default="auto",
        help="Media type for --process (default: auto-detect)",
    )
    parser.add_argument(
        "--scan-existing",
        action="store_true",
        help="Process all existing files on startup",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Clear failed entries from database for retry",
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
        service.running = True  # Enable processing
        service.process_single(args.process, args.type)
    else:
        # Service mode
        if args.scan_existing:
            logger.info("Processing existing files...")
            service.running = True  # Enable processing for scan-existing

            # Process existing movies
            if os.path.isdir(config["watch_directory"]):
                for entry in sorted(os.listdir(config["watch_directory"])):
                    entry_path = os.path.join(config["watch_directory"], entry)
                    service._process_movie_entry(entry_path)

            # Process existing TV shows
            tv_dir = config.get("tv_watch_directory")
            if tv_dir and os.path.isdir(tv_dir) and service.tv_watcher:
                for entry in sorted(os.listdir(tv_dir)):
                    entry_path = os.path.join(tv_dir, entry)
                    service._process_tv_entry(entry_path)

        service.start()


if __name__ == "__main__":
    main()

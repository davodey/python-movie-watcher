"""Media Sanitizer - watches directories and organizes with full TMDb metadata."""

import logging
import os
import time

from .database import ProcessedDatabase
from .organizer import MovieOrganizer, TVOrganizer
from .parser import parse_movie_filename, parse_tv_filename
from .tmdb import TMDbClient
from .watcher import MovieWatcher

logger = logging.getLogger(__name__)


class MediaSanitizer:
    """Watches directories for media files and organizes them with full metadata.

    Uses the same pipeline as the main Jellyfin organizer:
    - TMDb lookup for proper titles and metadata
    - Artwork download (poster, backdrop)
    - NFO file generation
    - Proper folder structure
    """

    def __init__(self, config):
        """
        Args:
            config: dict with keys:
                - tmdb_api_key: TMDb API key for metadata lookup
                - watch_directories: list of dicts with 'source' and 'destination' keys
                - video_extensions: list of video file extensions
                - subtitle_extensions: list of subtitle file extensions
                - min_file_size_mb: minimum file size to process
                - settle_time: seconds to wait for file to stabilize
                - scan_interval: seconds between scans
                - database_file: path to SQLite database for tracking
        """
        self.config = config
        self.running = False

        # Initialize shared components
        self.tmdb = TMDbClient(config["tmdb_api_key"])
        self.db = ProcessedDatabase(config.get("database_file", "/var/lib/media_sanitizer/processed.db"))

        # Create a watcher and organizer for each watch directory
        self.watch_configs = []
        subtitle_extensions = config.get("subtitle_extensions", [".srt", ".sub", ".ass", ".ssa", ".vtt", ".idx"])

        for watch_config in config.get("watch_directories", []):
            media_type = watch_config.get("media_type", "movies")

            watcher = MovieWatcher(
                watch_dir=watch_config["source"],
                video_extensions=config.get("video_extensions", [".mkv", ".mp4", ".avi", ".m4v"]),
                min_size_mb=config.get("min_file_size_mb", 100),
                settle_time=config.get("settle_time", 30),
            )

            # Use TV organizer for TV shows, movie organizer for movies
            if media_type == "tv":
                organizer = TVOrganizer(
                    destination_dir=watch_config["destination"],
                    subtitle_extensions=subtitle_extensions,
                )
            else:
                organizer = MovieOrganizer(
                    destination_dir=watch_config["destination"],
                    subtitle_extensions=subtitle_extensions,
                )

            self.watch_configs.append({
                "watcher": watcher,
                "organizer": organizer,
                "source": watch_config["source"],
                "destination": watch_config["destination"],
                "media_type": media_type,
            })

    def start(self):
        """Start the sanitizer service main loop."""
        self.running = True
        logger.info("=" * 60)
        logger.info("Media Sanitizer starting (with full TMDb metadata)")
        for w in self.watch_configs:
            logger.info("Watching: %s -> %s (%s)", w["source"], w["destination"], w["media_type"])
        logger.info("Scan interval: %d seconds", self.config.get("scan_interval", 60))
        logger.info("=" * 60)

        # Validate and create directories
        for w in self.watch_configs:
            if not os.path.isdir(w["source"]):
                logger.info("Creating watch directory: %s", w["source"])
                os.makedirs(w["source"], exist_ok=True)
            os.makedirs(w["destination"], exist_ok=True)

        # Initial scan to populate known entries
        logger.info("Performing initial scan to detect existing files...")
        for w in self.watch_configs:
            existing = w["watcher"].scan()
            logger.info("Found %d existing entries in %s (will not reprocess)",
                       len(existing), w["source"])

        scan_interval = self.config.get("scan_interval", 60)

        while self.running:
            try:
                self._scan_and_process()
            except Exception:
                logger.exception("Error during scan cycle")

            # Sleep in small increments for responsive shutdown
            for _ in range(scan_interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Media Sanitizer stopped")

    def stop(self):
        """Stop the sanitizer service."""
        logger.info("Stop signal received")
        self.running = False

    def _scan_and_process(self):
        """Run one scan cycle: detect new entries and process them."""
        for w in self.watch_configs:
            if not self.running:
                break

            new_entries = w["watcher"].scan()

            for entry_path in new_entries:
                if not self.running:
                    break
                self._process_entry(entry_path, w)

    def _process_entry(self, entry_path, watch_config):
        """Process a single new file or folder with full TMDb metadata.

        Args:
            entry_path: Path to the new entry in the watch directory.
            watch_config: dict with watcher, organizer, source, destination keys.
        """
        entry_name = os.path.basename(entry_path)
        watcher = watch_config["watcher"]
        organizer = watch_config["organizer"]
        media_type = watch_config["media_type"]

        logger.info("-" * 50)
        logger.info("New %s entry detected: %s", media_type, entry_name)

        # Check if already processed
        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping: %s", entry_name)
            return

        # Validate entry and find main video file
        video_path = watcher.validate_entry(entry_path)
        if not video_path:
            logger.info("No valid video file found, skipping: %s", entry_name)
            return

        # Wait for file to stabilize
        if not watcher.wait_for_stable(video_path):
            logger.warning("File not stable, skipping: %s", entry_name)
            return

        # Parse filename based on media type
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_path)

        if media_type == "tv":
            # TV show processing
            parsed = parse_tv_filename(parse_name)
            logger.info("Parsed TV: show='%s', S%02dE%02d",
                       parsed["show_name"],
                       parsed["season"] or 0,
                       parsed["episode"] or 0)

            # Search TMDb TV API
            logger.info("Searching TMDb TV for: %s", parsed["show_name"])
            tv_data = self.tmdb.get_full_tv_info(
                parsed["show_name"],
                parsed["season"],
                parsed["episode"]
            )

            if not tv_data:
                logger.warning("No TMDb TV match found for: %s", parsed["show_name"])
                self.db.mark_processed(entry_path, status="failed")
                return

            logger.info("TMDb TV match: %s [ID: %s]",
                       tv_data["show_name"], tv_data["tmdb_id"])
            if tv_data.get("episode_title"):
                logger.info("Episode: S%02dE%02d - %s",
                           parsed["season"] or 0,
                           parsed["episode"] or 0,
                           tv_data["episode_title"])

            # Organize the TV episode
            dest_folder = organizer.organize(
                video_path=video_path,
                source_entry=entry_path,
                tv_data=tv_data,
                parsed_info=parsed,
            )

            if dest_folder:
                self.db.mark_processed(
                    source_path=entry_path,
                    dest_path=dest_folder,
                    title=tv_data["show_name"],
                    year=tv_data.get("year"),
                    tmdb_id=tv_data.get("tmdb_id"),
                    status="success",
                )
                logger.info("SUCCESS: %s -> %s", entry_name, dest_folder)
            else:
                self.db.mark_processed(entry_path, status="failed")
                logger.error("FAILED: %s", entry_name)
        else:
            # Movie processing (default)
            parsed = parse_movie_filename(parse_name)
            logger.info("Parsed: title='%s', year=%s", parsed["title"], parsed["year"])

            # Search TMDb for metadata
            logger.info("Searching TMDb for: %s (%s)", parsed["title"], parsed["year"])
            movie_data = self.tmdb.get_full_movie_info(parsed["title"], parsed["year"])

            if not movie_data:
                logger.warning("No TMDb match found for: %s", parsed["title"])
                self.db.mark_processed(entry_path, status="failed")
                return

            logger.info("TMDb match: %s (%s) [ID: %s]",
                       movie_data["title"], movie_data["year"], movie_data["tmdb_id"])

            # Organize the movie
            dest_folder = organizer.organize(
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

    def process_existing(self):
        """Process all existing files in watch directories."""
        self.running = True  # Enable processing
        for w in self.watch_configs:
            source = w["source"]
            if not os.path.isdir(source):
                continue

            logger.info("Processing existing files in: %s", source)
            for entry in sorted(os.listdir(source)):
                if not self.running:
                    break
                entry_path = os.path.join(source, entry)
                self._process_entry(entry_path, w)

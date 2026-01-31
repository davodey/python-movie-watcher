"""Media file sanitizer - watches directories and sanitizes filenames."""

import logging
import os
import shutil
import signal
import time

from .parser import parse_movie_filename
from .watcher import MovieWatcher

logger = logging.getLogger(__name__)


def _sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames."""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")
    # Remove leading/trailing dots and spaces
    name = name.strip(". ")
    return name


class MediaSanitizer:
    """Watches directories for media files, sanitizes names, and moves them."""

    def __init__(self, config):
        """
        Args:
            config: dict with keys:
                - watch_directories: list of dicts with 'source' and 'destination' keys
                - video_extensions: list of video file extensions
                - min_file_size_mb: minimum file size to process
                - settle_time: seconds to wait for file to stabilize
                - scan_interval: seconds between scans
        """
        self.config = config
        self.running = False
        self.watchers = []

        # Create a watcher for each watch directory
        for watch_config in config.get("watch_directories", []):
            watcher = MovieWatcher(
                watch_dir=watch_config["source"],
                video_extensions=config.get("video_extensions", [".mkv", ".mp4", ".avi", ".m4v"]),
                min_size_mb=config.get("min_file_size_mb", 100),
                settle_time=config.get("settle_time", 30),
            )
            self.watchers.append({
                "watcher": watcher,
                "source": watch_config["source"],
                "destination": watch_config["destination"],
                "media_type": watch_config.get("media_type", "unknown"),
            })

    def start(self):
        """Start the sanitizer service main loop."""
        self.running = True
        logger.info("=" * 60)
        logger.info("Media Sanitizer starting")
        for w in self.watchers:
            logger.info("Watching: %s -> %s", w["source"], w["destination"])
        logger.info("Scan interval: %d seconds", self.config.get("scan_interval", 60))
        logger.info("=" * 60)

        # Validate and create directories
        for w in self.watchers:
            if not os.path.isdir(w["source"]):
                logger.info("Creating watch directory: %s", w["source"])
                os.makedirs(w["source"], exist_ok=True)
            os.makedirs(w["destination"], exist_ok=True)

        # Initial scan to populate known entries
        logger.info("Performing initial scan to detect existing files...")
        for w in self.watchers:
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
        for w in self.watchers:
            if not self.running:
                break

            new_entries = w["watcher"].scan()

            for entry_path in new_entries:
                if not self.running:
                    break
                self._process_entry(entry_path, w)

    def _process_entry(self, entry_path, watcher_config):
        """Process a single new file or folder.

        Args:
            entry_path: Path to the new entry in the watch directory.
            watcher_config: dict with watcher, source, destination keys.
        """
        entry_name = os.path.basename(entry_path)
        watcher = watcher_config["watcher"]
        destination = watcher_config["destination"]
        media_type = watcher_config["media_type"]

        logger.info("-" * 50)
        logger.info("New %s entry detected: %s", media_type, entry_name)

        # Validate entry and find main video file
        video_path = watcher.validate_entry(entry_path)
        if not video_path:
            logger.info("No valid video file found, skipping: %s", entry_name)
            return

        # Wait for file to stabilize
        if not watcher.wait_for_stable(video_path):
            logger.warning("File not stable, skipping: %s", entry_name)
            return

        # Parse and sanitize filename
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_path)
        parsed = parse_movie_filename(parse_name)
        logger.info("Parsed: title='%s', year=%s", parsed["title"], parsed["year"])

        # Build sanitized filename
        _, ext = os.path.splitext(video_path)
        if parsed["year"]:
            sanitized_name = f"{parsed['title']} ({parsed['year']}){ext}"
        else:
            sanitized_name = f"{parsed['title']}{ext}"

        sanitized_name = _sanitize_filename(sanitized_name)
        dest_path = os.path.join(destination, sanitized_name)

        # Handle name conflicts
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(sanitized_name)
            counter = 1
            while os.path.exists(dest_path):
                sanitized_name = f"{base} ({counter}){ext}"
                dest_path = os.path.join(destination, sanitized_name)
                counter += 1

        # Move the file
        try:
            logger.info("Moving: %s -> %s", os.path.basename(video_path), dest_path)
            shutil.move(video_path, dest_path)
            logger.info("SUCCESS: Moved to %s", dest_path)

            # Clean up source directory if it was a folder
            if os.path.isdir(entry_path):
                self._cleanup_source(entry_path)
            elif os.path.exists(entry_path) and entry_path != video_path:
                # entry_path was the video file itself, already moved
                pass

            logger.info("SUCCESS: %s sanitized and moved", entry_name)

        except Exception as e:
            logger.exception("Failed to move %s: %s", entry_name, e)

    def _cleanup_source(self, source_dir):
        """Remove source directory after moving video file.

        Args:
            source_dir: Path to the source directory to clean up.
        """
        # Check if directory still exists
        if not os.path.isdir(source_dir):
            return

        # Remove remaining files (subtitles, nfo, samples, etc.)
        try:
            for entry in os.listdir(source_dir):
                full_path = os.path.join(source_dir, entry)
                if os.path.isfile(full_path):
                    os.remove(full_path)
                    logger.debug("Removed leftover file: %s", entry)
                elif os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                    logger.debug("Removed leftover directory: %s", entry)

            # Remove the now-empty directory
            os.rmdir(source_dir)
            logger.info("Cleaned up source directory: %s", source_dir)

        except Exception as e:
            logger.warning("Could not fully clean up %s: %s", source_dir, e)

    def process_existing(self):
        """Process all existing files in watch directories."""
        for w in self.watchers:
            source = w["source"]
            if not os.path.isdir(source):
                continue

            logger.info("Processing existing files in: %s", source)
            for entry in sorted(os.listdir(source)):
                entry_path = os.path.join(source, entry)
                self._process_entry(entry_path, w)

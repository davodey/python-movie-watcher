"""File system watcher for detecting new movie downloads."""

import logging
import os
import time

logger = logging.getLogger(__name__)


class MovieWatcher:
    """Watches a directory for new movie files/folders."""

    def __init__(self, watch_dir, video_extensions, min_size_mb=100, settle_time=30):
        """
        Args:
            watch_dir: Directory to monitor.
            video_extensions: List of video file extensions.
            min_size_mb: Minimum file size in MB to consider valid.
            settle_time: Seconds to wait for file to stop changing.
        """
        self.watch_dir = watch_dir
        self.video_extensions = video_extensions
        self.min_size_bytes = min_size_mb * 1024 * 1024
        self.settle_time = settle_time
        self._known_entries = set()

    def scan(self):
        """Scan watch directory for new entries.

        Returns:
            list: New file/folder paths detected since last scan.
        """
        if not os.path.isdir(self.watch_dir):
            logger.warning("Watch directory does not exist: %s", self.watch_dir)
            return []

        current_entries = set()
        try:
            for entry in os.listdir(self.watch_dir):
                full_path = os.path.join(self.watch_dir, entry)
                current_entries.add(full_path)
        except PermissionError:
            logger.exception("Permission denied reading watch directory")
            return []

        new_entries = current_entries - self._known_entries
        self._known_entries = current_entries

        return sorted(new_entries)

    def validate_entry(self, path):
        """Validate that an entry is a processable movie.

        Args:
            path: Path to file or directory to validate.

        Returns:
            str or None: Path to the main video file, or None if invalid.
        """
        if os.path.isfile(path):
            return self._validate_file(path)
        elif os.path.isdir(path):
            return self._validate_directory(path)
        return None

    def _validate_file(self, filepath):
        """Validate a single video file."""
        _, ext = os.path.splitext(filepath)
        if ext.lower() not in self.video_extensions:
            logger.debug("Skipping non-video file: %s", filepath)
            return None

        size = os.path.getsize(filepath)
        if size < self.min_size_bytes:
            logger.debug("Skipping small file (%d MB): %s", size // (1024 * 1024), filepath)
            return None

        return filepath

    def _validate_directory(self, dirpath):
        """Find the main video file in a directory."""
        video_files = []
        for entry in os.listdir(dirpath):
            full_path = os.path.join(dirpath, entry)
            if os.path.isfile(full_path):
                _, ext = os.path.splitext(entry)
                if ext.lower() in self.video_extensions:
                    size = os.path.getsize(full_path)
                    if size >= self.min_size_bytes:
                        video_files.append((full_path, size))

        if not video_files:
            logger.debug("No valid video files found in: %s", dirpath)
            return None

        # Return the largest video file (most likely the main movie)
        video_files.sort(key=lambda x: x[1], reverse=True)
        return video_files[0][0]

    def wait_for_stable(self, filepath, check_interval=5, max_wait=1800):
        """Wait for a file to stop changing size (download complete).

        Checks immediately, then polls every 5 seconds until two consecutive
        checks show the same size. Supports large files (10GB+).

        Args:
            filepath: Path to the file to monitor.
            check_interval: Seconds between size checks.
            max_wait: Maximum total seconds to wait (default 30 minutes).

        Returns:
            bool: True if file is stable, False if it disappeared or timed out.
        """
        if not os.path.exists(filepath):
            logger.warning("File does not exist: %s", filepath)
            return False

        logger.info("Checking file stability: %s", filepath)
        elapsed = 0
        prev_size = os.path.getsize(filepath)

        while elapsed < max_wait:
            time.sleep(check_interval)
            elapsed += check_interval

            if not os.path.exists(filepath):
                logger.warning("File disappeared during stability check: %s", filepath)
                return False

            current_size = os.path.getsize(filepath)

            if current_size == prev_size:
                logger.info("File is stable (%d MB, waited %ds): %s",
                            current_size // (1024 * 1024), elapsed, filepath)
                return True

            logger.info("File still changing (%d MB -> %d MB, %ds elapsed): %s",
                        prev_size // (1024 * 1024),
                        current_size // (1024 * 1024),
                        elapsed, filepath)
            prev_size = current_size

        logger.warning("File still changing after %ds, giving up: %s", max_wait, filepath)
        return False

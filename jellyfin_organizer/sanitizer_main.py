#!/usr/bin/env python3
"""
Media Sanitizer with Complete TMDb Metadata & AI Enrichment via n8n

Monitors download folders, fetches comprehensive metadata from TMDb,
enriches with OpenAI via n8n webhook, creates NFO files, and organizes
media files for Jellyfin consumption.

Features:
- Complete TMDb metadata fetching (credits, keywords, images, collections)
- n8n webhook integration for AI content enrichment
- Jellyfin-compatible NFO file generation
- Quality-based duplicate detection and upgrade handling
- Collection tracking for playlist generation
- SQLite database for processing history and caching
"""

import argparse
import json
import logging
import os
import shutil
import signal
import sys
import time
from typing import Dict, List, Optional, Any

from .config import load_config
from .database import ProcessedDatabase
from .enricher import N8nEnricher, MockEnricher
from .metadata import NFOWriter
from .parser import (
    parse_movie_filename,
    parse_tv_filename,
    sanitize_filename,
    format_movie_folder_name,
    format_movie_filename,
    format_tv_episode_filename,
    find_video_files,
    find_subtitle_files,
)
from .tmdb import TMDbClient
from .watcher import MovieWatcher
from .artwork import download_movie_artwork

logger = logging.getLogger(__name__)


class MediaSanitizer:
    """Main orchestrator for media sanitization pipeline.

    Pipeline:
    1. Monitor folders for new media files
    2. Parse filenames to extract title, year, quality
    3. Fetch complete TMDb metadata
    4. Send to n8n webhook for AI enrichment
    5. Create Jellyfin-compatible NFO files
    6. Download artwork (posters, backdrops)
    7. Organize files into clean folder structure
    8. Track in database to prevent re-processing
    """

    def __init__(self, config: dict):
        """Initialize the media sanitizer.

        Args:
            config: Configuration dictionary with all settings.
        """
        self.config = config
        self.running = False

        # Initialize TMDb client
        tmdb_options = config.get("tmdb_options", {})
        self.tmdb = TMDbClient(
            api_key=config["tmdb_api_key"],
            image_base_url=tmdb_options.get("image_base_url"),
            language=tmdb_options.get("language", "en-US"),
        )

        # Initialize database
        db_path = config.get("database_path", config.get("database_file", "./sanitizer.db"))
        self.db = ProcessedDatabase(db_path)

        # Initialize n8n enricher
        n8n_config = config.get("n8n_options", {})
        n8n_url = config.get("n8n_webhook_url")
        if n8n_url:
            self.enricher = N8nEnricher(
                webhook_url=n8n_url,
                timeout=n8n_config.get("timeout", 30),
                retry_count=n8n_config.get("retry_count", 3),
            )
        else:
            logger.warning("n8n webhook URL not configured, using mock enricher")
            self.enricher = MockEnricher()

        # Initialize NFO writer
        self.nfo_writer = NFOWriter()

        # Initialize watchers for each folder
        self.watch_configs = self._setup_watchers(config)

        # File settings
        self.video_extensions = config.get("file_extensions", config.get("video_extensions", [".mkv", ".mp4", ".avi", ".m4v"]))
        self.subtitle_extensions = config.get("subtitle_extensions", [".srt", ".sub", ".ass", ".ssa", ".vtt"])
        self.min_file_size_mb = config.get("min_file_size_mb", 100)

    def _setup_watchers(self, config: dict) -> List[dict]:
        """Setup file watchers for configured directories.

        Args:
            config: Configuration dictionary.

        Returns:
            List of watcher configurations.
        """
        watchers = []

        # Support both old and new config formats
        watch_folders = config.get("watch_folders", {})
        output_folders = config.get("output_folders", {})
        watch_directories = config.get("watch_directories", [])

        # New format: watch_folders and output_folders
        if watch_folders and output_folders:
            # Movie watcher
            if watch_folders.get("movies") and output_folders.get("movies"):
                watchers.append({
                    "media_type": "movie",
                    "source": watch_folders["movies"],
                    "destination": output_folders["movies"],
                    "watcher": MovieWatcher(
                        watch_dir=watch_folders["movies"],
                        video_extensions=config.get("file_extensions", [".mkv", ".mp4", ".avi"]),
                        min_size_mb=config.get("min_file_size_mb", 100),
                        settle_time=config.get("settle_time", 30),
                    ),
                })

            # TV watcher
            if watch_folders.get("tv") and output_folders.get("tv"):
                watchers.append({
                    "media_type": "tv",
                    "source": watch_folders["tv"],
                    "destination": output_folders["tv"],
                    "watcher": MovieWatcher(
                        watch_dir=watch_folders["tv"],
                        video_extensions=config.get("file_extensions", [".mkv", ".mp4", ".avi"]),
                        min_size_mb=config.get("min_file_size_mb", 100),
                        settle_time=config.get("settle_time", 30),
                    ),
                })

        # Old format: watch_directories list
        elif watch_directories:
            for wd in watch_directories:
                media_type = wd.get("media_type", "movies")
                if media_type == "movies":
                    media_type = "movie"

                watchers.append({
                    "media_type": media_type,
                    "source": wd["source"],
                    "destination": wd["destination"],
                    "watcher": MovieWatcher(
                        watch_dir=wd["source"],
                        video_extensions=config.get("video_extensions", [".mkv", ".mp4", ".avi"]),
                        min_size_mb=config.get("min_file_size_mb", 100),
                        settle_time=config.get("settle_time", 30),
                    ),
                })

        return watchers

    def start(self):
        """Start the media sanitizer main loop."""
        self.running = True
        interval = self.config.get("watch_interval", self.config.get("scan_interval", 60))

        logger.info("=" * 60)
        logger.info("Media Sanitizer starting")
        logger.info("Complete TMDb metadata + n8n AI enrichment enabled")
        for w in self.watch_configs:
            logger.info("Watching %s: %s -> %s", w["media_type"], w["source"], w["destination"])
        logger.info("Scan interval: %d seconds", interval)
        logger.info("=" * 60)

        # Ensure directories exist
        self._ensure_directories()

        # Initial scan
        logger.info("Performing initial scan...")
        for w in self.watch_configs:
            existing = w["watcher"].scan()
            logger.info("Found %d existing entries in %s", len(existing), w["source"])

        # Main loop
        while self.running:
            try:
                self._scan_and_process()
            except Exception:
                logger.exception("Error during scan cycle")

            # Sleep in small increments for responsive shutdown
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("Media Sanitizer stopped")

    def stop(self):
        """Stop the media sanitizer."""
        logger.info("Stop signal received")
        self.running = False

    def _ensure_directories(self):
        """Create watch and destination directories."""
        for w in self.watch_configs:
            os.makedirs(w["source"], exist_ok=True)
            os.makedirs(w["destination"], exist_ok=True)

    def _scan_and_process(self):
        """Run one scan cycle."""
        for w in self.watch_configs:
            if not self.running:
                break

            for entry_path in w["watcher"].scan():
                if not self.running:
                    break

                if w["media_type"] == "movie":
                    self._process_movie(entry_path, w)
                else:
                    self._process_tv_episode(entry_path, w)

    def _process_movie(self, entry_path: str, watch_config: dict):
        """Process a movie file through the full pipeline.

        Args:
            entry_path: Path to the movie file or folder.
            watch_config: Watcher configuration.
        """
        entry_name = os.path.basename(entry_path)
        logger.info("-" * 50)
        logger.info("[MOVIE] New entry: %s", entry_name)

        # Check if already processed
        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping")
            return

        # Validate and find video file
        watcher = watch_config["watcher"]
        video_path = watcher.validate_entry(entry_path)
        if not video_path:
            logger.warning("No valid video file found, skipping")
            return

        # Wait for file to be stable
        if not watcher.wait_for_stable(video_path):
            logger.warning("File not stable, skipping")
            return

        # Parse filename
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_path)
        parsed = parse_movie_filename(parse_name)
        logger.info("Parsed: title='%s', year=%s, quality=%s (score: %d)",
                   parsed["title"], parsed["year"], parsed["quality"], parsed["quality_score"])

        # Fetch TMDb metadata
        logger.info("Fetching TMDb metadata...")
        tmdb_data = self.tmdb.get_full_movie_info(parsed["title"], parsed["year"])

        if not tmdb_data:
            logger.warning("No TMDb match found for: %s", parsed["title"])
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("TMDb match: %s (%s) [ID: %s]",
                   tmdb_data["title"], tmdb_data["year"], tmdb_data["tmdb_id"])

        # Log comprehensive metadata
        cast_count = len(tmdb_data.get("cast", []))
        keyword_count = len(tmdb_data.get("keywords", []))
        collection_name = tmdb_data.get("collection", {}).get("name") if tmdb_data.get("collection") else None
        logger.info("Metadata: cast=%d, keywords=%d, collection=%s",
                   cast_count, keyword_count, collection_name or "None")

        # Check for duplicates/upgrades
        should_process, reason, existing = self.db.should_process(
            tmdb_data["tmdb_id"], "movie", parsed["quality_score"]
        )

        if not should_process:
            logger.info("Duplicate detected (existing quality: %d), skipping",
                       existing.get("quality_score", 0) if existing else 0)
            return

        if reason == "upgrade":
            logger.info("Quality upgrade detected! Old: %d, New: %d",
                       existing.get("quality_score", 0), parsed["quality_score"])

        # Send to n8n for AI enrichment (optional - processing continues even if this fails)
        logger.info("Sending to n8n for AI enrichment...")
        enriched_data = self.enricher.enrich_movie(tmdb_data)

        if enriched_data:
            logger.info("AI enrichment complete (age: %s, tags: %d)",
                       enriched_data.get("age_recommendation", "N/A"),
                       len(enriched_data.get("custom_tags", [])))
        else:
            logger.info("AI enrichment unavailable, continuing with TMDb data only")
            # Create a copy to avoid mutating the original tmdb_data
            enriched_data = tmdb_data.copy()
            enriched_data["enriched"] = False

        # Organize files
        try:
            dest_folder = self._organize_movie(
                video_path=video_path,
                source_entry=entry_path,
                enriched_data=enriched_data,
                parsed_info=parsed,
                destination=watch_config["destination"],
            )
        except Exception:
            logger.exception("Failed to organize movie")
            self.db.mark_processed(entry_path, status="failed")
            return

        # Track collection
        if tmdb_data.get("collection"):
            self.db.add_to_collection(
                collection_id=tmdb_data["collection"]["id"],
                collection_name=tmdb_data["collection"]["name"],
                movie_tmdb_id=tmdb_data["tmdb_id"],
                movie_title=tmdb_data["title"],
            )

        # Mark as processed
        self.db.mark_processed(
            source_path=entry_path,
            dest_path=dest_folder,
            title=tmdb_data["title"],
            year=tmdb_data.get("year"),
            tmdb_id=tmdb_data.get("tmdb_id"),
            media_type="movie",
            enriched=enriched_data.get("enriched", False),
            quality_score=parsed["quality_score"],
            source_type=parsed.get("source"),
        )

        # Log enrichment
        if enriched_data.get("enriched"):
            self.db.log_enrichment(
                tmdb_id=tmdb_data["tmdb_id"],
                media_type="movie",
                title=tmdb_data["title"],
                enrichment_data=enriched_data,
            )

        logger.info("SUCCESS: %s -> %s", entry_name, dest_folder)

    def _organize_movie(
        self,
        video_path: str,
        source_entry: str,
        enriched_data: dict,
        parsed_info: dict,
        destination: str,
    ) -> str:
        """Organize a movie file into the destination library.

        Args:
            video_path: Path to the video file.
            source_entry: Original source entry (file or folder).
            enriched_data: Combined TMDb + AI enriched metadata.
            parsed_info: Parsed filename info.
            destination: Base destination directory.

        Returns:
            str: Destination folder path.
        """
        title = enriched_data.get("title", parsed_info.get("title", "Unknown"))
        year = enriched_data.get("year") or parsed_info.get("year")

        # Create folder name
        folder_name = format_movie_folder_name(title, year)
        dest_folder = os.path.join(destination, folder_name)

        # Handle existing folder
        if os.path.exists(dest_folder):
            timestamp = int(time.time())
            dest_folder = f"{dest_folder}_{timestamp}"

        os.makedirs(dest_folder, exist_ok=True)
        logger.info("Created: %s", dest_folder)

        # Move video file
        video_ext = os.path.splitext(video_path)[1]
        quality_str = parsed_info.get("quality", "")
        if quality_str and quality_str != "Unknown":
            video_filename = format_movie_filename(title, year, quality_str, video_ext)
        else:
            video_filename = format_movie_filename(title, year, None, video_ext)

        dest_video = os.path.join(dest_folder, video_filename)
        logger.info("Moving: %s", os.path.basename(dest_video))
        shutil.move(video_path, dest_video)

        # Move subtitles
        if os.path.isdir(source_entry):
            for sub_path in find_subtitle_files(source_entry, self.subtitle_extensions):
                sub_dest = os.path.join(dest_folder, os.path.basename(sub_path))
                shutil.move(sub_path, sub_dest)
                logger.info("Moved subtitle: %s", os.path.basename(sub_path))

        # Create NFO file
        nfo_filename = os.path.splitext(video_filename)[0] + ".nfo"
        nfo_path = os.path.join(dest_folder, nfo_filename)
        self.nfo_writer.create_movie_nfo(enriched_data, nfo_path)

        # Download artwork
        art_results = download_movie_artwork(enriched_data, dest_folder)
        if art_results.get("poster"):
            logger.info("Poster downloaded")
        if art_results.get("backdrop"):
            logger.info("Backdrop downloaded")

        # Cleanup source
        if os.path.isdir(source_entry):
            self._cleanup_source(source_entry)

        return dest_folder

    def _process_tv_episode(self, entry_path: str, watch_config: dict):
        """Process a TV episode through the full pipeline.

        Args:
            entry_path: Path to the TV episode file or folder.
            watch_config: Watcher configuration.
        """
        entry_name = os.path.basename(entry_path)
        logger.info("-" * 50)
        logger.info("[TV] New entry: %s", entry_name)

        # Check if already processed
        if self.db.is_processed(entry_path):
            logger.info("Already processed, skipping")
            return

        # Find video files
        video_files = self._find_tv_videos(entry_path)
        if not video_files:
            logger.warning("No valid video files found, skipping")
            return

        # Parse first file to get show info
        parse_name = entry_name if os.path.isdir(entry_path) else os.path.basename(video_files[0])
        parsed = parse_tv_filename(parse_name)

        if not parsed.get("show_name"):
            logger.warning("Could not parse as TV show: %s", parse_name)
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("Parsed: show='%s', S%02dE%02d, quality=%s",
                   parsed["show_name"],
                   parsed.get("season") or 0,
                   parsed.get("episode") or 0,
                   parsed.get("quality", "Unknown"))

        # Fetch TMDb show data
        logger.info("Fetching TMDb TV metadata...")
        show_data = self.tmdb.get_full_tv_info(parsed["show_name"], parsed.get("year"))

        if not show_data:
            logger.warning("No TMDb TV match found for: %s", parsed["show_name"])
            self.db.mark_processed(entry_path, status="failed")
            return

        logger.info("TMDb match: %s (%s) [ID: %s]",
                   show_data.get("title"), show_data.get("year"), show_data.get("tmdb_id"))

        # Enrich show data (optional - processing continues even if this fails)
        logger.info("Sending to n8n for AI enrichment...")
        enriched_show_data = self.enricher.enrich_tv_show(show_data)

        if enriched_show_data:
            logger.info("AI enrichment complete")
        else:
            logger.info("AI enrichment unavailable, continuing with TMDb data only")
            # Create a copy to avoid mutating the original show_data
            enriched_show_data = show_data.copy()
            enriched_show_data["enriched"] = False

        # Process each video file
        success_count = 0
        destination = watch_config["destination"]

        for video_path in video_files:
            if not self.running:
                break

            try:
                # Parse this specific episode
                ep_parsed = parse_tv_filename(os.path.basename(video_path))
                if not ep_parsed.get("season") or not ep_parsed.get("episode"):
                    ep_parsed = parsed

                # Get episode metadata
                episode_data = None
                if ep_parsed.get("season") and ep_parsed.get("episode"):
                    episode_data = self.tmdb.get_full_episode_info(
                        show_data["tmdb_id"],
                        ep_parsed["season"],
                        ep_parsed["episode"],
                    )

                # Organize episode
                self._organize_tv_episode(
                    video_path=video_path,
                    show_data=enriched_show_data,
                    episode_data=episode_data,
                    parsed_info=ep_parsed,
                    destination=destination,
                )
                success_count += 1

            except PermissionError as e:
                logger.error("Permission denied for episode %s: %s", os.path.basename(video_path), e)
            except FileNotFoundError as e:
                logger.error("File not found for episode %s: %s", os.path.basename(video_path), e)
            except OSError as e:
                logger.error("OS error for episode %s: %s", os.path.basename(video_path), e)
            except Exception:
                logger.exception("Failed to organize episode: %s", os.path.basename(video_path))

        # Cleanup and mark processed
        if success_count > 0:
            if os.path.isdir(entry_path):
                self._cleanup_source(entry_path)

            self.db.mark_processed(
                source_path=entry_path,
                dest_path=destination,
                title=show_data.get("title"),
                year=show_data.get("year"),
                tmdb_id=show_data.get("tmdb_id"),
                media_type="tv",
                enriched=enriched_show_data.get("enriched", False),
                quality_score=parsed.get("quality_score", 0),
            )

            logger.info("SUCCESS: %s (%d episodes)", entry_name, success_count)
        else:
            self.db.mark_processed(entry_path, status="failed")
            logger.error("FAILED: %s", entry_name)

    def _organize_tv_episode(
        self,
        video_path: str,
        show_data: dict,
        episode_data: Optional[dict],
        parsed_info: dict,
        destination: str,
    ):
        """Organize a TV episode file.

        Args:
            video_path: Path to the video file.
            show_data: Show metadata.
            episode_data: Episode-specific metadata.
            parsed_info: Parsed filename info.
            destination: Base destination directory.
        """
        show_name = show_data.get("title", "") or show_data.get("show_name", "") or parsed_info.get("show_name", "Unknown Show")
        show_name = sanitize_filename(show_name)

        if not show_name or show_name == "Unknown Show":
            logger.warning("Could not determine show name, using parsed name: %s", parsed_info.get("show_name", "Unknown"))
            show_name = sanitize_filename(parsed_info.get("show_name", "Unknown Show"))

        season = parsed_info.get("season") or 1
        episode = parsed_info.get("episode") or 1

        # Create show folder
        show_folder = os.path.join(destination, show_name)
        os.makedirs(show_folder, exist_ok=True)

        # Create tvshow.nfo if it doesn't exist
        tvshow_nfo_path = os.path.join(show_folder, "tvshow.nfo")
        if not os.path.exists(tvshow_nfo_path):
            self.nfo_writer.create_tvshow_nfo(show_data, tvshow_nfo_path)
            # Download show artwork
            download_movie_artwork(show_data, show_folder)

        # Create season folder
        season_folder = os.path.join(show_folder, f"Season {season:02d}")
        os.makedirs(season_folder, exist_ok=True)

        # Build episode filename
        video_ext = os.path.splitext(video_path)[1]
        episode_title = ""
        if episode_data:
            episode_title = episode_data.get("title", "") or episode_data.get("episode_title", "")

        video_filename = format_tv_episode_filename(show_name, season, episode, episode_title, video_ext)
        dest_video = os.path.join(season_folder, video_filename)

        # Handle conflicts
        if os.path.exists(dest_video):
            timestamp = int(time.time())
            base = os.path.splitext(video_filename)[0]
            video_filename = f"{base}_{timestamp}{video_ext}"
            dest_video = os.path.join(season_folder, video_filename)

        # Verify source exists before moving
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Source video file does not exist: {video_path}")

        # Move video
        logger.info("Moving: %s -> %s", os.path.basename(video_path), dest_video)
        shutil.move(video_path, dest_video)
        logger.debug("Move successful")

        # Create episode NFO
        if episode_data:
            nfo_path = os.path.splitext(dest_video)[0] + ".nfo"
            self.nfo_writer.create_episode_nfo(episode_data, show_data, nfo_path)

    def _find_tv_videos(self, entry_path: str) -> List[str]:
        """Find all video files in a TV entry.

        Args:
            entry_path: Path to file or directory.

        Returns:
            list: Sorted list of video file paths.
        """
        videos = []
        min_size = self.min_file_size_mb * 1024 * 1024
        video_exts = set(self.video_extensions)

        if os.path.isfile(entry_path):
            _, ext = os.path.splitext(entry_path)
            if ext.lower() in video_exts:
                try:
                    if os.path.getsize(entry_path) >= min_size:
                        videos.append(entry_path)
                except OSError:
                    pass
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

    def _cleanup_source(self, source_dir: str):
        """Remove source directory if empty or only has junk files."""
        try:
            remaining = os.listdir(source_dir)
            junk_extensions = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".url", ".html", ".exe"}
            all_junk = all(
                os.path.splitext(f)[1].lower() in junk_extensions
                for f in remaining
                if os.path.isfile(os.path.join(source_dir, f))
            )

            if not remaining or all_junk:
                shutil.rmtree(source_dir)
                logger.info("Removed source: %s", source_dir)
        except Exception:
            logger.exception("Failed to cleanup: %s", source_dir)

    def process_single(self, path: str, media_type: str = "auto"):
        """Process a single file or folder on-demand.

        Args:
            path: Path to process.
            media_type: 'movie', 'tv', or 'auto' to detect.
        """
        if not os.path.exists(path):
            logger.error("Path does not exist: %s", path)
            return False

        path = os.path.abspath(path)

        # Auto-detect media type
        if media_type == "auto":
            name = os.path.basename(path)
            parsed = parse_tv_filename(name)
            if parsed.get("season") or parsed.get("episode"):
                media_type = "tv"
            else:
                media_type = "movie"

        # Find appropriate watcher config
        watch_config = None
        for w in self.watch_configs:
            if w["media_type"] == media_type:
                watch_config = w
                break

        if not watch_config:
            logger.error("No configuration found for media type: %s", media_type)
            return False

        self.running = True

        if media_type == "tv":
            self._process_tv_episode(path, watch_config)
        else:
            self._process_movie(path, watch_config)

        return True

    def process_existing(self):
        """Process all existing files in watch directories."""
        self.running = True
        for w in self.watch_configs:
            source = w["source"]
            if not os.path.isdir(source):
                continue

            logger.info("Processing existing files in: %s", source)
            for entry in sorted(os.listdir(source)):
                if not self.running:
                    break
                entry_path = os.path.join(source, entry)

                if w["media_type"] == "movie":
                    self._process_movie(entry_path, w)
                else:
                    self._process_tv_episode(entry_path, w)


def setup_logging(log_file: str):
    """Configure logging to file and console.

    Args:
        log_file: Path to log file.
    """
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
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
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Media Sanitizer - Complete TMDb metadata + AI enrichment",
    )
    parser.add_argument(
        "-c", "--config",
        default="sanitizer_config.json",
        help="Path to config file (default: sanitizer_config.json)",
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
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show processing statistics and exit",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Setup logging
    log_file = config.get("log_file", "./sanitizer.log")
    setup_logging(log_file)

    # Create sanitizer
    sanitizer = MediaSanitizer(config)

    # Handle signals
    def signal_handler(signum, frame):
        sanitizer.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Stats mode
    if args.stats:
        stats = sanitizer.db.get_stats()
        print("\n=== Media Sanitizer Statistics ===")
        print(f"Total processed: {stats['total_processed']}")
        print(f"Total failed: {stats['total_failed']}")
        print(f"Enriched: {stats['enriched']}")
        print(f"Collections tracked: {stats['collections']}")
        print(f"By type: {stats['by_type']}")
        return

    # Retry failed mode
    if args.retry_failed:
        cleared = sanitizer.db.clear_failed()
        logger.info("Cleared %d failed entries for retry", cleared)

    # Single file mode
    if args.process:
        sanitizer.process_single(args.process, args.type)
        return

    # Scan existing mode
    if args.scan_existing:
        logger.info("Processing existing files...")
        sanitizer.process_existing()

    # Normal service mode
    sanitizer.start()


if __name__ == "__main__":
    main()

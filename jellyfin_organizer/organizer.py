"""File organization - moving and structuring movie files."""

import logging
import os
import shutil
import time

from . import metadata as metadata_mod
from .artwork import download_movie_artwork
from .parser import find_subtitle_files

logger = logging.getLogger(__name__)


class MovieOrganizer:
    """Handles moving and organizing movie files into the destination library."""

    def __init__(self, destination_dir, subtitle_extensions):
        """
        Args:
            destination_dir: Base destination directory for organized movies.
            subtitle_extensions: List of subtitle file extensions.
        """
        self.destination_dir = destination_dir
        self.subtitle_extensions = subtitle_extensions

    def organize(self, video_path, source_entry, movie_data, parsed_info):
        """Organize a movie file into the destination library.

        This is the main orchestration method that:
        1. Creates the destination folder
        2. Moves the video file
        3. Moves any subtitle files
        4. Creates the NFO metadata file
        5. Downloads artwork

        Args:
            video_path: Path to the main video file.
            source_entry: Path to the original source entry (file or folder).
            movie_data: TMDb metadata dict.
            parsed_info: Parsed filename info dict.

        Returns:
            str or None: Destination folder path on success, None on failure.
        """
        # Use the official TMDb title and year for a clean, standard folder name
        title = movie_data.get("title", parsed_info.get("title", "Movie"))
        year = movie_data.get("year") or parsed_info.get("year")
        title = _sanitize_filename(title)

        if year:
            folder_name = f"{title} ({year})"
        else:
            folder_name = title

        dest_folder = os.path.join(self.destination_dir, folder_name)

        # Handle duplicate folder names
        if os.path.exists(dest_folder):
            timestamp = int(time.time())
            dest_folder = f"{dest_folder}_{timestamp}"
            logger.info("Destination exists, using: %s", dest_folder)

        try:
            return self._do_organize(
                video_path, source_entry, dest_folder, movie_data, parsed_info
            )
        except Exception:
            logger.exception("Organization failed, attempting rollback")
            self._rollback(dest_folder)
            return None

    def _do_organize(self, video_path, source_entry, dest_folder, movie_data, parsed_info):
        """Perform the actual organization with atomic-style operations."""
        # Step 1: Create destination folder
        os.makedirs(dest_folder, exist_ok=True)
        logger.info("Created destination: %s", dest_folder)

        # Step 2: Determine destination video filename using TMDb official title
        title = movie_data.get("title", parsed_info.get("title", "Movie"))
        year = movie_data.get("year") or parsed_info.get("year")
        title = _sanitize_filename(title)
        video_ext = os.path.splitext(video_path)[1]

        if year:
            video_filename = f"{title} ({year}){video_ext}"
        else:
            video_filename = f"{title}{video_ext}"
        dest_video = os.path.join(dest_folder, video_filename)

        # Step 3: Move video file
        logger.info("Moving video: %s -> %s", video_path, dest_video)
        shutil.move(video_path, dest_video)

        # Step 4: Move subtitle files (if source is a directory)
        if os.path.isdir(source_entry):
            subtitles = find_subtitle_files(source_entry, self.subtitle_extensions)
            for sub_path in subtitles:
                sub_dest = os.path.join(dest_folder, os.path.basename(sub_path))
                logger.info("Moving subtitle: %s -> %s", sub_path, sub_dest)
                shutil.move(sub_path, sub_dest)

        # Step 5: Create NFO metadata file
        nfo_filename = os.path.splitext(video_filename)[0] + ".nfo"
        nfo_path = os.path.join(dest_folder, nfo_filename)
        metadata_mod.write_nfo_file(nfo_path, movie_data)

        # Step 6: Download artwork
        art_results = download_movie_artwork(movie_data, dest_folder)
        if art_results["poster"]:
            logger.info("Poster downloaded successfully")
        else:
            logger.warning("Poster download failed or unavailable")
        if art_results["backdrop"]:
            logger.info("Backdrop downloaded successfully")
        else:
            logger.warning("Backdrop download failed or unavailable")

        # Step 7: Clean up empty source directory
        if os.path.isdir(source_entry):
            self._cleanup_source(source_entry)

        logger.info("Organization complete: %s", dest_folder)
        return dest_folder

    def _cleanup_source(self, source_dir):
        """Remove the source directory if it's empty or only has junk files."""
        try:
            remaining = os.listdir(source_dir)
            # Allow removal if only non-important files remain (txt, nfo, jpg, png, etc.)
            junk_extensions = {".txt", ".nfo", ".jpg", ".jpeg", ".png", ".url", ".html", ".exe"}
            all_junk = all(
                os.path.splitext(f)[1].lower() in junk_extensions
                for f in remaining
                if os.path.isfile(os.path.join(source_dir, f))
            )

            if not remaining or all_junk:
                shutil.rmtree(source_dir)
                logger.info("Removed source directory: %s", source_dir)
            else:
                logger.info("Source directory not empty, keeping: %s", source_dir)
        except Exception:
            logger.exception("Failed to clean up source directory: %s", source_dir)

    def _rollback(self, dest_folder):
        """Remove partially created destination on failure."""
        if os.path.exists(dest_folder):
            try:
                shutil.rmtree(dest_folder)
                logger.info("Rolled back: %s", dest_folder)
            except Exception:
                logger.exception("Rollback failed for: %s", dest_folder)


def _sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames.

    Args:
        name: Filename to sanitize.

    Returns:
        str: Sanitized filename.
    """
    # Replace problematic characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")
    # Remove leading/trailing dots and spaces
    name = name.strip(". ")
    return name

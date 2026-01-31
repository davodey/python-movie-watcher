"""TV show organization - moving and structuring TV episode files."""

import logging
import os
import shutil

from .artwork import download_image
from .metadata import write_tvshow_nfo, write_episode_nfo
from .parser import find_subtitle_files

logger = logging.getLogger(__name__)


class TVOrganizer:
    """Handles organizing TV show episodes into the destination library.

    Structure created:
        Show Name (Year)/
            tvshow.nfo
            poster.jpg
            backdrop.jpg (fanart.jpg)
            Season 01/
                Show Name - S01E01 - Episode Title.mkv
                Show Name - S01E01 - Episode Title.nfo
                Show Name - S01E02.mkv
                ...
    """

    def __init__(self, destination_dir, subtitle_extensions):
        """
        Args:
            destination_dir: Base destination directory for organized TV shows.
            subtitle_extensions: List of subtitle file extensions.
        """
        self.destination_dir = destination_dir
        self.subtitle_extensions = subtitle_extensions
        # Cache of show folders we've created (tmdb_id -> folder path)
        self._show_cache = {}

    def organize_episode(self, video_path, source_entry, show_data, episode_data, parsed_info):
        """Organize a single TV episode into the library.

        Args:
            video_path: Path to the episode video file.
            source_entry: Path to the original source entry (file or folder).
            show_data: TMDb TV show metadata dict.
            episode_data: TMDb episode metadata dict (can be None).
            parsed_info: Parsed filename info dict.

        Returns:
            str or None: Destination episode path on success, None on failure.
        """
        try:
            return self._do_organize_episode(
                video_path, source_entry, show_data, episode_data, parsed_info
            )
        except Exception:
            logger.exception("TV organization failed for: %s", video_path)
            return None

    def _do_organize_episode(self, video_path, source_entry, show_data, episode_data, parsed_info):
        """Perform the actual episode organization."""
        # Step 1: Get or create the show folder
        show_folder = self._get_or_create_show_folder(show_data)

        # Step 2: Create season folder
        season_num = parsed_info.get("season", 1)
        season_folder = os.path.join(show_folder, f"Season {season_num:02d}")
        os.makedirs(season_folder, exist_ok=True)

        # Step 3: Build episode filename
        show_title = _sanitize_filename(show_data.get("title", parsed_info.get("show", "Show")))
        episode_num = parsed_info.get("episode")
        video_ext = os.path.splitext(video_path)[1]

        if episode_data and episode_data.get("title"):
            # Include episode title if we have it
            ep_title = _sanitize_filename(episode_data["title"])
            episode_filename = f"{show_title} - S{season_num:02d}E{episode_num:02d} - {ep_title}{video_ext}"
        elif episode_num:
            episode_filename = f"{show_title} - S{season_num:02d}E{episode_num:02d}{video_ext}"
        else:
            # Season pack or unknown - keep original name
            episode_filename = os.path.basename(video_path)

        dest_episode = os.path.join(season_folder, episode_filename)

        # Handle duplicates
        if os.path.exists(dest_episode):
            base, ext = os.path.splitext(episode_filename)
            counter = 1
            while os.path.exists(dest_episode):
                dest_episode = os.path.join(season_folder, f"{base} ({counter}){ext}")
                counter += 1

        # Step 4: Move video file
        logger.info("Moving episode: %s -> %s", video_path, dest_episode)
        shutil.move(video_path, dest_episode)

        # Step 5: Move subtitle files (if source is a directory and contains subtitles)
        if os.path.isdir(source_entry):
            subtitles = find_subtitle_files(source_entry, self.subtitle_extensions)
            for sub_path in subtitles:
                # Try to match subtitle to this episode
                sub_name = os.path.basename(sub_path)
                if self._subtitle_matches_episode(sub_name, season_num, episode_num):
                    sub_ext = os.path.splitext(sub_path)[1]
                    dest_sub = os.path.splitext(dest_episode)[0] + sub_ext
                    logger.info("Moving subtitle: %s -> %s", sub_path, dest_sub)
                    shutil.move(sub_path, dest_sub)

        # Step 6: Write episode NFO
        if episode_data:
            write_episode_nfo(dest_episode, episode_data, show_data)

        logger.info("Episode organized: %s", dest_episode)
        return dest_episode

    def _get_or_create_show_folder(self, show_data):
        """Get or create the show folder, creating tvshow.nfo and artwork if new.

        Args:
            show_data: TMDb TV show metadata dict.

        Returns:
            str: Path to the show folder.
        """
        tmdb_id = show_data.get("tmdb_id")

        # Check cache first
        if tmdb_id and tmdb_id in self._show_cache:
            return self._show_cache[tmdb_id]

        # Build folder name: "Show Name (Year)"
        show_title = _sanitize_filename(show_data.get("title", "Unknown Show"))
        year = show_data.get("year")

        if year:
            folder_name = f"{show_title} ({year})"
        else:
            folder_name = show_title

        show_folder = os.path.join(self.destination_dir, folder_name)

        # Check if folder already exists (maybe from previous run)
        if os.path.exists(show_folder):
            if tmdb_id:
                self._show_cache[tmdb_id] = show_folder
            return show_folder

        # Create new show folder
        os.makedirs(show_folder, exist_ok=True)
        logger.info("Created show folder: %s", show_folder)

        # Write tvshow.nfo
        write_tvshow_nfo(show_folder, show_data)

        # Download artwork
        self._download_show_artwork(show_data, show_folder)

        if tmdb_id:
            self._show_cache[tmdb_id] = show_folder

        return show_folder

    def _download_show_artwork(self, show_data, show_folder):
        """Download poster and backdrop for a TV show.

        Args:
            show_data: TMDb TV show metadata dict.
            show_folder: Path to the show folder.
        """
        # Download poster
        if show_data.get("poster_url"):
            poster_path = os.path.join(show_folder, "poster.jpg")
            if download_image(show_data["poster_url"], poster_path):
                logger.info("Show poster downloaded: %s", poster_path)

        # Download backdrop (also save as fanart.jpg for compatibility)
        if show_data.get("backdrop_url"):
            backdrop_path = os.path.join(show_folder, "fanart.jpg")
            if download_image(show_data["backdrop_url"], backdrop_path):
                logger.info("Show backdrop downloaded: %s", backdrop_path)

    def _subtitle_matches_episode(self, sub_name, season, episode):
        """Check if a subtitle filename matches a specific episode.

        Args:
            sub_name: Subtitle filename.
            season: Season number.
            episode: Episode number.

        Returns:
            bool: True if subtitle appears to match this episode.
        """
        import re
        sub_lower = sub_name.lower()

        # Match S01E01 pattern
        match = re.search(r's(\d{1,2})e(\d{1,3})', sub_lower)
        if match:
            return int(match.group(1)) == season and int(match.group(2)) == episode

        # Match 1x01 pattern
        match = re.search(r'(\d{1,2})x(\d{1,3})', sub_lower)
        if match:
            return int(match.group(1)) == season and int(match.group(2)) == episode

        return False

    def cleanup_source(self, source_dir):
        """Remove source directory if empty or only contains junk files.

        Args:
            source_dir: Path to the source directory to clean up.
        """
        if not os.path.isdir(source_dir):
            return

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
                logger.info("Removed source directory: %s", source_dir)
            else:
                logger.info("Source directory not empty, keeping: %s", source_dir)
        except Exception:
            logger.exception("Failed to clean up source directory: %s", source_dir)


def _sanitize_filename(name):
    """Remove or replace characters that are invalid in filenames.

    Args:
        name: Filename to sanitize.

    Returns:
        str: Sanitized filename.
    """
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        name = name.replace(char, "")
    name = name.strip(". ")
    return name

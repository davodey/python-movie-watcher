"""Intelligent filename parsing for torrent movie and TV show files."""

import os
import re


# Patterns to strip from filenames (order matters)
STRIP_PATTERNS = [
    # Website tags
    r'\bwww\.[a-zA-Z0-9\-]+\.[a-zA-Z]+\b',
    # Release groups (at end, after dash)
    r'-[A-Za-z0-9]+(?:\.[A-Za-z]+)?$',
    # Bracketed tags
    r'\[(?:UNCUT|REMASTERED|EXTENDED|DIRECTORS\.?CUT|IMAX|3D|HDR|'
    r'DV|HYBRID|PROPER|REPACK|INTERNAL|LIMITED|THEATRICAL|FINAL\.?CUT|'
    r'CRITERION|RESTORED|ANNIVERSARY|SPECIAL\.?EDITION)\]',
    # Resolution
    r'\b(?:2160|1080|720|480|360)[pi]?\b',
    r'\b4[Kk]\b',
    r'\bUHD\b',
    # Video source
    r'\b(?:WEB[-\.]?DL|WEB[-\.]?Rip|WEBRip|BluRay|Blu[-\.]?Ray|BDRip|BRRip|'
    r'HDRip|HDTV|DVDRip|DVDScr|DVDR|CAM|TS|TC|TELESYNC|TELECINE|'
    r'REMUX|AMZN|NF|DSNP|HMAX|ATVP|PMTP|PCOK|MA|IT|CRAV|STAN)\b',
    # Video codec
    r'\b(?:x264|x265|[Hh]\.?264|[Hh]\.?265|HEVC|AVC|VP9|AV1|XviD|DivX|MPEG[24]?|10bit)\b',
    # HDR formats
    r'\b(?:HDR10(?:\+|Plus)?|HDR|DV|Dolby\.?Vision|HLG|DDP?)\b',
    # Audio codec
    r'\b(?:AAC(?:2\.0|5\.1)?|AC3|EAC3|DTS(?:-HD)?(?:\.?MA)?|TrueHD|FLAC|'
    r'Atmos|DD[P\+]?[257]?\.?[01]?|[257]\.1|LPCM|Opus|Vorbis)\b',
    # Audio channels
    r'\b[257]\.[01]\b',
    # Common tags (unbracketed)
    r'\b(?:UNCUT|REMASTERED|EXTENDED|DIRECTORS\.?CUT|IMAX|PROPER|REPACK|'
    r'INTERNAL|LIMITED|THEATRICAL|MULTI|DUAL|MULTi|COMPLETE|FiNAL)\b',
    # Encoder/group tags
    r'\b(?:YTS\.?(?:MX|LT|AM)?|RARBG|YIFY|Tigole|QxR|SPARKS|GECKOS|'
    r'FGT|EVO|STUTTERSHIT|AMRAP|FLUX|CM|NTb|SMURF|ION10|NOSiViD|'
    r'SiGMA|DRONES|FraMeSToR|BHDStudio|playWEB|EDITH|HONE)\b',
    # Extra dots and spaces cleanup (run last)
    r'\.{2,}',
]

# Year pattern: 4 digits that look like a year (1900-2099)
YEAR_PATTERN = re.compile(r'[\.\s\(]?((?:19|20)\d{2})[\.\s\)]?')

# TV episode patterns (order matters - try most specific first)
TV_EPISODE_PATTERNS = [
    # S01E01 or S01E01E02 (multi-episode)
    re.compile(r'[.\s]S(\d{1,2})E(\d{1,3})(?:E\d{1,3})*[.\s]', re.IGNORECASE),
    # S01.E01 or S01 E01
    re.compile(r'[.\s]S(\d{1,2})[.\s]?E(\d{1,3})[.\s]', re.IGNORECASE),
    # 1x01 format
    re.compile(r'[.\s](\d{1,2})x(\d{1,3})[.\s]', re.IGNORECASE),
    # Season 1 Episode 1
    re.compile(r'Season[.\s]?(\d{1,2})[.\s]?Episode[.\s]?(\d{1,3})', re.IGNORECASE),
]

# Season-only patterns (for season packs)
TV_SEASON_PATTERNS = [
    # S01 or Season 1 (without episode)
    re.compile(r'[.\s]S(\d{1,2})(?:[.\s]|$)(?!E)', re.IGNORECASE),
    re.compile(r'Season[.\s]?(\d{1,2})(?:[.\s]|$)', re.IGNORECASE),
]


# Known video file extensions to strip
VIDEO_EXTENSIONS = {
    '.mkv', '.mp4', '.avi', '.m4v', '.mov', '.wmv', '.flv', '.webm',
    '.mpg', '.mpeg', '.m2ts', '.ts', '.vob', '.divx', '.iso',
}


def parse_movie_filename(filename):
    """Parse a torrent movie filename into title and year.

    Args:
        filename: The filename or folder name to parse (with or without extension).

    Returns:
        dict with keys:
            - title: Cleaned movie title
            - year: Year as int, or None if not found
            - original: Original filename
    """
    original = filename

    # Only strip known video extensions (not arbitrary ones like .org)
    name, ext = os.path.splitext(filename)
    if ext.lower() not in VIDEO_EXTENSIONS:
        name = filename

    # Replace dots and underscores with spaces early so patterns match cleanly
    name = name.replace('.', ' ').replace('_', ' ')

    # Strip leading website tags like "www SiteName org - " or "www SiteName com  -  "
    name = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', name, flags=re.IGNORECASE)

    # Find year first (we'll use it to truncate the name)
    year = None
    year_match = YEAR_PATTERN.search(name)
    if year_match:
        year = int(year_match.group(1))
        # Truncate everything after the year
        year_pos = year_match.start()
        name = name[:year_pos]

    # Apply strip patterns to catch anything before the year too
    for pattern in STRIP_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

    # Remove any remaining bracketed content
    name = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', name)

    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Remove trailing dashes or dots
    name = name.rstrip('- .')

    # Title case if all uppercase
    if name == name.upper() and len(name) > 3:
        name = name.title()

    return {
        "title": name,
        "year": year,
        "original": original,
    }


def find_video_files(directory, video_extensions):
    """Find all video files in a directory.

    Args:
        directory: Path to search.
        video_extensions: List of video file extensions (e.g. ['.mkv', '.mp4']).

    Returns:
        List of absolute paths to video files.
    """
    video_files = []
    if os.path.isfile(directory):
        _, ext = os.path.splitext(directory)
        if ext.lower() in video_extensions:
            video_files.append(directory)
    elif os.path.isdir(directory):
        for entry in os.listdir(directory):
            full_path = os.path.join(directory, entry)
            if os.path.isfile(full_path):
                _, ext = os.path.splitext(entry)
                if ext.lower() in video_extensions:
                    video_files.append(full_path)
    return video_files


def find_subtitle_files(directory, subtitle_extensions):
    """Find all subtitle files in a directory.

    Args:
        directory: Path to search.
        subtitle_extensions: List of subtitle file extensions.

    Returns:
        List of absolute paths to subtitle files.
    """
    subtitle_files = []
    if os.path.isdir(directory):
        for entry in os.listdir(directory):
            full_path = os.path.join(directory, entry)
            if os.path.isfile(full_path):
                _, ext = os.path.splitext(entry)
                if ext.lower() in subtitle_extensions:
                    subtitle_files.append(full_path)
    return subtitle_files


def parse_tv_filename(filename):
    """Parse a torrent TV show filename into show name, season, and episode.

    Args:
        filename: The filename or folder name to parse.

    Returns:
        dict with keys:
            - show: Cleaned show name
            - season: Season number as int, or None
            - episode: Episode number as int, or None
            - year: Year as int, or None (for show premiere year)
            - is_season_pack: True if this appears to be a full season
            - original: Original filename
        Returns None if no TV pattern is detected.
    """
    original = filename

    # Only strip known video extensions
    name, ext = os.path.splitext(filename)
    if ext.lower() not in VIDEO_EXTENSIONS:
        name = filename

    # Replace dots and underscores with spaces
    name_spaced = name.replace('.', ' ').replace('_', ' ')

    # Strip leading website tags
    name_spaced = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', name_spaced, flags=re.IGNORECASE)

    # Try to find episode pattern first (most common)
    season = None
    episode = None
    match_pos = None

    for pattern in TV_EPISODE_PATTERNS:
        match = pattern.search(name)
        if match:
            season = int(match.group(1))
            episode = int(match.group(2))
            match_pos = match.start()
            break

    # If no episode found, check for season pack
    is_season_pack = False
    if season is None:
        for pattern in TV_SEASON_PATTERNS:
            match = pattern.search(name)
            if match:
                season = int(match.group(1))
                is_season_pack = True
                match_pos = match.start()
                break

    # If no TV pattern found, return None
    if season is None:
        return None

    # Extract show name (everything before the season/episode marker)
    show_name = name[:match_pos] if match_pos else name

    # Clean up show name
    show_name = show_name.replace('.', ' ').replace('_', ' ')

    # Strip website prefixes from show name
    show_name = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', show_name, flags=re.IGNORECASE)

    # Try to extract year from show name (e.g., "The Office 2005")
    year = None
    year_match = YEAR_PATTERN.search(show_name)
    if year_match:
        year = int(year_match.group(1))
        # Remove year from show name
        show_name = show_name[:year_match.start()] + show_name[year_match.end():]

    # Apply strip patterns
    for pattern in STRIP_PATTERNS:
        show_name = re.sub(pattern, ' ', show_name, flags=re.IGNORECASE)

    # Remove bracketed content
    show_name = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', show_name)

    # Clean up whitespace
    show_name = re.sub(r'\s+', ' ', show_name).strip()
    show_name = show_name.rstrip('- .')

    # Title case if all uppercase
    if show_name == show_name.upper() and len(show_name) > 3:
        show_name = show_name.title()

    return {
        "show": show_name,
        "season": season,
        "episode": episode,
        "year": year,
        "is_season_pack": is_season_pack,
        "original": original,
    }


def is_tv_show(filename):
    """Check if a filename appears to be a TV show (has season/episode markers).

    Args:
        filename: The filename to check.

    Returns:
        bool: True if this looks like a TV show episode.
    """
    return parse_tv_filename(filename) is not None

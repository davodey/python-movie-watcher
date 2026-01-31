"""Intelligent filename parsing for torrent movie files."""

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

# TV show episode pattern: S01E01, S1E1, S01.E01, 1x01, etc.
TV_EPISODE_PATTERN = re.compile(
    r'[.\s_-]*[Ss](\d{1,2})[.\s_-]*[Ee](\d{1,3})(?:[.\s_-]*[Ee]\d{1,3})?'  # S01E01, S01.E01, or S01E01E02
    r'|[.\s_-]*(\d{1,2})[xX](\d{1,3})',  # 1x01 format
    re.IGNORECASE
)

# Quality/release tags in brackets to strip early (before parsing)
BRACKET_QUALITY_PATTERN = re.compile(
    r'[\[\(](?:'
    r'2160p?|1080p?|720p?|480p?|4K|UHD|'  # Resolution
    r'BluRay|Blu-Ray|BDRip|BRRip|WEB-?DL|WEBRip|HDTV|HDRip|DVDRip|REMUX|'  # Source
    r'x264|x265|H\.?264|H\.?265|HEVC|AVC|10bit|'  # Codec
    r'AAC|AC3|DTS|TrueHD|Atmos|DD5\.1|DD7\.1|5\.1|7\.1|'  # Audio
    r'YTS\.?(?:MX|LT|AM)?|RARBG|YIFY|Tigole|QxR|SPARKS|FGT|EVO|'  # Release groups
    r'HDR(?:10)?|DV|Dolby\.?Vision|'  # HDR
    r'EXTENDED|REMASTERED|UNCUT|PROPER|REPACK|DUAL|MULTI'  # Tags
    r')[^\]\)]*[\]\)]',
    re.IGNORECASE
)

# "Season X" redundancy pattern (when followed by SXX or standalone)
SEASON_REDUNDANCY_PATTERN = re.compile(
    r'\bSeason\s*(\d{1,2})\s*(?=[Ss]\1)',  # "Season 2 S02" -> remove "Season 2 "
    re.IGNORECASE
)


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

    # Remove file extension if present
    name, _ = os.path.splitext(filename)

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


def parse_tv_filename(filename):
    """Parse a torrent TV show filename into show name, season, and episode.

    Args:
        filename: The filename or folder name to parse (with or without extension).

    Returns:
        dict with keys:
            - show_name: Cleaned show title
            - season: Season number as int, or None
            - episode: Episode number as int, or None
            - original: Original filename
    """
    original = filename

    # Remove file extension if present
    name, _ = os.path.splitext(filename)

    # Replace dots and underscores with spaces
    name = name.replace('.', ' ').replace('_', ' ')

    # Strip quality tags in brackets early (1080p), [BluRay], [YTS.MX], etc.
    name = BRACKET_QUALITY_PATTERN.sub(' ', name)

    # Strip leading website tags
    name = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', name, flags=re.IGNORECASE)

    # Handle "Season X SXX" redundancy (e.g., "Season 2 S02E01" -> "S02E01")
    name = SEASON_REDUNDANCY_PATTERN.sub('', name)

    # Find and extract season/episode info
    season = None
    episode = None
    ep_match = TV_EPISODE_PATTERN.search(name)

    if ep_match:
        # S01E01 format
        if ep_match.group(1) and ep_match.group(2):
            season = int(ep_match.group(1))
            episode = int(ep_match.group(2))
        # 1x01 format
        elif ep_match.group(3) and ep_match.group(4):
            season = int(ep_match.group(3))
            episode = int(ep_match.group(4))

        # Check if episode pattern is at the start (S00E45 - Show Name format)
        # Allow for leading whitespace/separators
        match_start = ep_match.start()
        prefix = name[:match_start].strip()

        if not prefix or prefix in ['-', '–', '—']:
            # Episode info at the start - extract show name from after the pattern
            after_ep = name[ep_match.end():].strip()
            # Remove leading separator (dash, colon, etc.)
            name = re.sub(r'^[\s\-–—:]+', '', after_ep)
        else:
            # Normal format - truncate name at the episode pattern
            name = name[:ep_match.start()]

    # Apply strip patterns
    for pattern in STRIP_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

    # Remove any remaining bracketed content
    name = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', name)

    # Remove "Season X" if present (for folder names like "Show - Season 2")
    name = re.sub(r'\s*-?\s*[Ss]eason\s*\d+\s*$', '', name)

    # Clean up whitespace
    name = re.sub(r'\s+', ' ', name).strip()

    # Remove trailing dashes or dots
    name = name.rstrip('- .')

    # Title case if all lowercase
    if name == name.lower() and len(name) > 3:
        name = name.title()

    return {
        "show_name": name,
        "season": season,
        "episode": episode,
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

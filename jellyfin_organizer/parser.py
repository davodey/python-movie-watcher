"""Enhanced filename parsing for torrent media files with quality scoring."""

import os
import re
from typing import Dict, List, Optional, Tuple

# ==================== Quality Scoring ====================

# Source quality scores (higher = better)
SOURCE_SCORES = {
    "REMUX": 100,
    "UHD.BLURAY": 95,
    "BLURAY": 90,
    "BLU-RAY": 90,
    "BDRIP": 85,
    "BRRIP": 80,
    "WEB-DL": 75,
    "WEBDL": 75,
    "WEBRIP": 70,
    "WEB-RIP": 70,
    "WEB": 65,
    "HDTV": 60,
    "HDRIP": 55,
    "DVDRIP": 50,
    "DVDSCR": 40,
    "DVDR": 45,
    "HDCAM": 30,
    "HDTS": 25,
    "TS": 20,
    "TELESYNC": 20,
    "TC": 15,
    "TELECINE": 15,
    "CAM": 10,
    "CAMRIP": 10,
}

# Resolution scores
RESOLUTION_SCORES = {
    "2160P": 40,
    "4K": 40,
    "UHD": 40,
    "1080P": 30,
    "1080I": 28,
    "720P": 20,
    "576P": 15,
    "480P": 10,
    "SD": 5,
}

# HDR bonuses
HDR_BONUSES = {
    "DOLBY.VISION": 15,
    "DOLBYVISION": 15,
    "DV": 15,
    "HDR10+": 12,
    "HDR10PLUS": 12,
    "HDR10": 10,
    "HDR": 8,
    "HLG": 5,
}

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

# TV show episode pattern: S01E01, S1E1, 1x01, etc.
TV_EPISODE_PATTERN = re.compile(
    r'[.\s_-]*[Ss](\d{1,2})[Ee](\d{1,2})(?:[Ee]\d{1,2})?'  # S01E01 or S01E01E02
    r'|[.\s_-]*(\d{1,2})[xX](\d{1,2})',  # 1x01 format
    re.IGNORECASE
)


def parse_movie_filename(filename: str) -> dict:
    """Parse a torrent movie filename into title, year, and quality info.

    Args:
        filename: The filename or folder name to parse (with or without extension).

    Returns:
        dict with keys:
            - title: Cleaned movie title
            - year: Year as int, or None if not found
            - quality: Quality string (e.g., "1080p BluRay")
            - quality_score: Numeric quality score for comparison
            - source: Source type (BluRay, WEB-DL, etc.)
            - resolution: Resolution (1080p, 2160p, etc.)
            - hdr: HDR type if present
            - group: Release group name
            - original: Original filename
    """
    original = filename

    # Remove file extension if present
    name, _ = os.path.splitext(filename)

    # Extract quality info BEFORE cleaning the filename
    quality_info = extract_quality_info(name)

    # Replace dots and underscores with spaces
    name = name.replace('.', ' ').replace('_', ' ')

    # Strip leading website tags
    name = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', name, flags=re.IGNORECASE)

    # Find year first (we'll use it to truncate the name)
    year = None
    year_match = YEAR_PATTERN.search(name)
    if year_match:
        year = int(year_match.group(1))
        # Truncate everything after the year
        year_pos = year_match.start()
        name = name[:year_pos]

    # Apply strip patterns
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
        "quality": quality_info["quality_string"],
        "quality_score": quality_info["total_score"],
        "source": quality_info["source"],
        "resolution": quality_info["resolution"],
        "hdr": quality_info["hdr"],
        "group": quality_info["group"],
        "original": original,
    }


def parse_tv_filename(filename: str) -> dict:
    """Parse a torrent TV show filename into show name, season, episode, and quality.

    Args:
        filename: The filename or folder name to parse (with or without extension).

    Returns:
        dict with keys:
            - show_name: Cleaned show title
            - season: Season number as int, or None
            - episode: Episode number as int, or None
            - year: Year as int, or None
            - quality: Quality string
            - quality_score: Numeric quality score
            - source: Source type
            - resolution: Resolution
            - group: Release group name
            - original: Original filename
    """
    original = filename

    # Remove file extension if present
    name, _ = os.path.splitext(filename)

    # Extract quality info BEFORE cleaning
    quality_info = extract_quality_info(name)

    # Replace dots and underscores with spaces
    name = name.replace('.', ' ').replace('_', ' ')

    # Strip leading website tags
    name = re.sub(r'^www\s+\S+\s+\S+\s*[-–—:]+\s*', '', name, flags=re.IGNORECASE)

    # Find and extract season/episode info
    season = None
    episode = None
    year = None
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

        # Truncate name at the episode pattern
        name = name[:ep_match.start()]
    else:
        # Try to find year for shows without episode info
        year_match = YEAR_PATTERN.search(name)
        if year_match:
            year = int(year_match.group(1))
            name = name[:year_match.start()]

    # Apply strip patterns
    for pattern in STRIP_PATTERNS:
        name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)

    # Remove any remaining bracketed content
    name = re.sub(r'[\[\(][^\]\)]*[\]\)]', ' ', name)

    # Remove "Season X" if present
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
        "show": name,  # Alias for compatibility
        "season": season,
        "episode": episode,
        "year": year,
        "quality": quality_info["quality_string"],
        "quality_score": quality_info["total_score"],
        "source": quality_info["source"],
        "resolution": quality_info["resolution"],
        "group": quality_info["group"],
        "original": original,
    }


def extract_quality_info(filename: str) -> dict:
    """Extract quality information from a filename.

    Args:
        filename: Filename to analyze.

    Returns:
        dict with quality details:
            - source: Source type (BluRay, WEB-DL, etc.)
            - resolution: Resolution (1080p, 2160p, etc.)
            - hdr: HDR type if present
            - group: Release group
            - quality_string: Formatted quality string
            - source_score: Score for source type
            - resolution_score: Score for resolution
            - hdr_bonus: Bonus score for HDR
            - total_score: Combined quality score
    """
    filename_upper = filename.upper()

    # Extract source
    source = None
    source_score = 0
    for src, score in SOURCE_SCORES.items():
        # Handle variations with dots and dashes
        patterns = [
            src,
            src.replace('.', ''),
            src.replace('.', '-'),
            src.replace('-', '.'),
            src.replace('-', ''),
        ]
        for pattern in patterns:
            if pattern in filename_upper:
                if score > source_score:
                    source = src.replace('.', ' ').replace('-', ' ').title()
                    source_score = score
                break

    # Extract resolution
    resolution = None
    resolution_score = 0
    for res, score in RESOLUTION_SCORES.items():
        if res in filename_upper:
            if score > resolution_score:
                resolution = res.lower()
                resolution_score = score

    # Extract HDR
    hdr = None
    hdr_bonus = 0
    for hdr_type, bonus in HDR_BONUSES.items():
        patterns = [hdr_type, hdr_type.replace('.', '')]
        for pattern in patterns:
            if pattern in filename_upper:
                if bonus > hdr_bonus:
                    hdr = hdr_type.replace('.', ' ')
                    hdr_bonus = bonus
                break

    # Extract release group (last segment after dash)
    group = None
    group_match = re.search(r'-([A-Za-z0-9]+)(?:\.[A-Za-z]+)?$', filename)
    if group_match:
        group = group_match.group(1)

    # Build quality string
    parts = []
    if resolution:
        parts.append(resolution)
    if source:
        parts.append(source)
    if hdr:
        parts.append(hdr)
    quality_string = " ".join(parts) if parts else "Unknown"

    return {
        "source": source,
        "resolution": resolution,
        "hdr": hdr,
        "group": group,
        "quality_string": quality_string,
        "source_score": source_score,
        "resolution_score": resolution_score,
        "hdr_bonus": hdr_bonus,
        "total_score": source_score + resolution_score + hdr_bonus,
    }


def calculate_quality_score(filename: str) -> int:
    """Calculate a quality score for a media file based on its filename.

    Args:
        filename: The filename to analyze.

    Returns:
        int: Quality score (higher is better).
    """
    info = extract_quality_info(filename)
    return info["total_score"]


def compare_quality(filename1: str, filename2: str) -> int:
    """Compare quality of two files.

    Args:
        filename1: First filename.
        filename2: Second filename.

    Returns:
        int: Positive if file1 is better, negative if file2 is better, 0 if equal.
    """
    score1 = calculate_quality_score(filename1)
    score2 = calculate_quality_score(filename2)
    return score1 - score2


def is_upgrade(existing_filename: str, new_filename: str) -> bool:
    """Check if a new file is an upgrade over an existing one.

    Args:
        existing_filename: Existing file's name.
        new_filename: New file's name.

    Returns:
        bool: True if new file is higher quality.
    """
    return compare_quality(new_filename, existing_filename) > 0


def find_video_files(directory: str, video_extensions: List[str]) -> List[str]:
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


def find_subtitle_files(directory: str, subtitle_extensions: List[str]) -> List[str]:
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


def sanitize_filename(name: str) -> str:
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


def format_movie_folder_name(title: str, year: int = None) -> str:
    """Format a movie folder name.

    Args:
        title: Movie title.
        year: Optional release year.

    Returns:
        str: Formatted folder name.
    """
    title = sanitize_filename(title)
    if year:
        return f"{title} ({year})"
    return title


def format_movie_filename(title: str, year: int = None, quality: str = None, ext: str = ".mkv") -> str:
    """Format a movie filename.

    Args:
        title: Movie title.
        year: Optional release year.
        quality: Optional quality string to include.
        ext: File extension (default: .mkv).

    Returns:
        str: Formatted filename.
    """
    title = sanitize_filename(title)

    parts = [title]
    if year:
        parts.append(f"({year})")
    if quality:
        parts.append(f"[{quality}]")

    return " ".join(parts) + ext


def format_tv_episode_filename(
    show_name: str,
    season: int,
    episode: int,
    episode_title: str = None,
    ext: str = ".mkv"
) -> str:
    """Format a TV episode filename.

    Args:
        show_name: Show name.
        season: Season number.
        episode: Episode number.
        episode_title: Optional episode title.
        ext: File extension (default: .mkv).

    Returns:
        str: Formatted filename.
    """
    show_name = sanitize_filename(show_name)
    episode_code = f"S{season:02d}E{episode:02d}"

    if episode_title:
        episode_title = sanitize_filename(episode_title)
        return f"{show_name} - {episode_code} - {episode_title}{ext}"
    return f"{show_name} - {episode_code}{ext}"

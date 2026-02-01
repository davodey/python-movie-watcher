"""Enhanced SQLite database for tracking processed files, metadata cache, and collections."""

import json
import logging
import os
import sqlite3
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ProcessedDatabase:
    """Enhanced database for tracking processed files, caching metadata, and managing collections.

    Tables:
    - processed_files: Track which files have been processed
    - metadata_cache: Cache TMDb API responses
    - collections: Track movie collections for playlist generation
    - quality_scores: Track file quality for upgrade detection
    """

    def __init__(self, db_path: str):
        """Initialize database.

        Args:
            db_path: Path to SQLite database file.
        """
        self.db_path = db_path
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self):
        """Create the database directory if it doesn't exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _init_db(self):
        """Initialize the database schema with all required tables."""
        with self._connect() as conn:
            # Main processed files table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT UNIQUE NOT NULL,
                    tmdb_id INTEGER,
                    media_type TEXT,
                    title TEXT,
                    year INTEGER,
                    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    enriched BOOLEAN DEFAULT 0,
                    moved_to TEXT,
                    quality_score INTEGER DEFAULT 0,
                    source_type TEXT,
                    status TEXT DEFAULT 'success'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_file_path
                ON processed_files(file_path)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_processed_tmdb_id
                ON processed_files(tmdb_id)
            """)

            # Metadata cache table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metadata_cache (
                    tmdb_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    data TEXT,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tmdb_id, media_type)
                )
            """)

            # Collections table for playlist generation
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tmdb_collection_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    movie_tmdb_id INTEGER,
                    movie_title TEXT,
                    chronological_order INTEGER,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(tmdb_collection_id, movie_tmdb_id)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_collections_tmdb_id
                ON collections(tmdb_collection_id)
            """)

            # Enrichment log table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS enrichment_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tmdb_id INTEGER,
                    media_type TEXT,
                    title TEXT,
                    enriched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    enrichment_data TEXT,
                    success BOOLEAN DEFAULT 1
                )
            """)

    def _connect(self) -> sqlite3.Connection:
        """Create a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ==================== Processed Files ====================

    def is_processed(self, file_path: str) -> bool:
        """Check if a file/folder has already been processed successfully.

        Args:
            file_path: Original source path of the file.

        Returns:
            bool: True if already processed successfully.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM processed_files WHERE file_path = ? AND status = 'success'",
                (file_path,),
            )
            count = cursor.fetchone()[0]
            return count > 0

    def mark_processed(
        self,
        source_path: str,
        dest_path: str = None,
        title: str = None,
        year: int = None,
        tmdb_id: int = None,
        media_type: str = None,
        enriched: bool = False,
        quality_score: int = 0,
        source_type: str = None,
        status: str = "success"
    ):
        """Record a file as processed.

        Args:
            source_path: Original source path.
            dest_path: Destination path after organization.
            title: Media title.
            year: Release year.
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.
            enriched: Whether AI enrichment was performed.
            quality_score: Quality score for upgrade detection.
            source_type: Source type (BluRay, WEB-DL, etc.).
            status: Processing status ('success', 'failed', 'skipped').
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO processed_files
                   (file_path, tmdb_id, media_type, title, year, processed_at,
                    enriched, moved_to, quality_score, source_type, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (source_path, tmdb_id, media_type, title, year, time.time(),
                 enriched, dest_path, quality_score, source_type, status),
            )
        logger.info("Recorded processed: %s (%s)", source_path, status)

    def get_by_tmdb_id(self, tmdb_id: int, media_type: str = None) -> Optional[dict]:
        """Get processed file info by TMDb ID.

        Args:
            tmdb_id: TMDb ID.
            media_type: Optional filter by media type.

        Returns:
            dict or None: Processed file info if found.
        """
        with self._connect() as conn:
            if media_type:
                cursor = conn.execute(
                    "SELECT * FROM processed_files WHERE tmdb_id = ? AND media_type = ? AND status = 'success'",
                    (tmdb_id, media_type),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM processed_files WHERE tmdb_id = ? AND status = 'success'",
                    (tmdb_id,),
                )
            row = cursor.fetchone()
            return dict(row) if row else None

    def check_for_upgrade(self, tmdb_id: int, new_quality_score: int, media_type: str = "movie") -> Optional[dict]:
        """Check if a new file is an upgrade over an existing one.

        Args:
            tmdb_id: TMDb ID.
            new_quality_score: Quality score of new file.
            media_type: Media type.

        Returns:
            dict or None: Existing file info if upgrade is available, None otherwise.
        """
        existing = self.get_by_tmdb_id(tmdb_id, media_type)
        if existing and existing.get("quality_score", 0) < new_quality_score:
            return existing
        return None

    def clear_failed(self) -> int:
        """Remove all failed entries so they can be retried.

        Returns:
            int: Number of entries cleared.
        """
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM processed_files WHERE status = 'failed'")
            count = cursor.rowcount
        logger.info("Cleared %d failed entries from database", count)
        return count

    def get_recent(self, limit: int = 20, media_type: str = None) -> List[dict]:
        """Get recently processed entries.

        Args:
            limit: Maximum number of entries to return.
            media_type: Optional filter by media type.

        Returns:
            list of dicts with processing info.
        """
        with self._connect() as conn:
            if media_type:
                cursor = conn.execute(
                    "SELECT * FROM processed_files WHERE media_type = ? ORDER BY processed_at DESC LIMIT ?",
                    (media_type, limit),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM processed_files ORDER BY processed_at DESC LIMIT ?",
                    (limit,),
                )
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> dict:
        """Get processing statistics.

        Returns:
            dict with statistics.
        """
        with self._connect() as conn:
            stats = {}

            # Total counts
            cursor = conn.execute("SELECT COUNT(*) FROM processed_files WHERE status = 'success'")
            stats["total_processed"] = cursor.fetchone()[0]

            cursor = conn.execute("SELECT COUNT(*) FROM processed_files WHERE status = 'failed'")
            stats["total_failed"] = cursor.fetchone()[0]

            # By media type
            cursor = conn.execute(
                "SELECT media_type, COUNT(*) FROM processed_files WHERE status = 'success' GROUP BY media_type"
            )
            stats["by_type"] = {row[0]: row[1] for row in cursor.fetchall()}

            # Enrichment stats
            cursor = conn.execute("SELECT COUNT(*) FROM processed_files WHERE enriched = 1")
            stats["enriched"] = cursor.fetchone()[0]

            # Collections count
            cursor = conn.execute("SELECT COUNT(DISTINCT tmdb_collection_id) FROM collections")
            stats["collections"] = cursor.fetchone()[0]

            return stats

    # ==================== Metadata Cache ====================

    def cache_metadata(self, tmdb_id: int, media_type: str, data: dict):
        """Cache TMDb metadata.

        Args:
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.
            data: Metadata dict to cache.
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO metadata_cache (tmdb_id, media_type, data, cached_at)
                   VALUES (?, ?, ?, ?)""",
                (tmdb_id, media_type, json.dumps(data), time.time()),
            )
        logger.debug("Cached metadata for %s %d", media_type, tmdb_id)

    def get_cached_metadata(self, tmdb_id: int, media_type: str, max_age_hours: int = 24) -> Optional[dict]:
        """Get cached metadata if not expired.

        Args:
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.
            max_age_hours: Maximum cache age in hours.

        Returns:
            dict or None: Cached metadata if valid, None otherwise.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT data, cached_at FROM metadata_cache WHERE tmdb_id = ? AND media_type = ?",
                (tmdb_id, media_type),
            )
            row = cursor.fetchone()
            if row:
                cached_at = row["cached_at"]
                age_hours = (time.time() - cached_at) / 3600
                if age_hours <= max_age_hours:
                    return json.loads(row["data"])
        return None

    def clear_metadata_cache(self, max_age_hours: int = 168):
        """Clear old metadata cache entries.

        Args:
            max_age_hours: Clear entries older than this (default 7 days).

        Returns:
            int: Number of entries cleared.
        """
        cutoff = time.time() - (max_age_hours * 3600)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM metadata_cache WHERE cached_at < ?",
                (cutoff,),
            )
            count = cursor.rowcount
        logger.info("Cleared %d old cache entries", count)
        return count

    # ==================== Collections ====================

    def add_to_collection(
        self,
        collection_id: int,
        collection_name: str,
        movie_tmdb_id: int,
        movie_title: str,
        chronological_order: int = None
    ):
        """Add a movie to a collection.

        Args:
            collection_id: TMDb collection ID.
            collection_name: Collection name.
            movie_tmdb_id: TMDb movie ID.
            movie_title: Movie title.
            chronological_order: Optional chronological order in collection.
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO collections
                   (tmdb_collection_id, name, movie_tmdb_id, movie_title, chronological_order)
                   VALUES (?, ?, ?, ?, ?)""",
                (collection_id, collection_name, movie_tmdb_id, movie_title, chronological_order),
            )
        logger.debug("Added %s to collection %s", movie_title, collection_name)

    def get_collection(self, collection_id: int) -> List[dict]:
        """Get all movies in a collection.

        Args:
            collection_id: TMDb collection ID.

        Returns:
            list of dicts with movie info.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """SELECT * FROM collections
                   WHERE tmdb_collection_id = ?
                   ORDER BY COALESCE(chronological_order, movie_tmdb_id)""",
                (collection_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get_all_collections(self) -> List[dict]:
        """Get all collections with movie counts.

        Returns:
            list of dicts with collection info.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                """SELECT tmdb_collection_id, name, COUNT(*) as movie_count
                   FROM collections
                   GROUP BY tmdb_collection_id
                   ORDER BY name"""
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Enrichment Log ====================

    def log_enrichment(
        self,
        tmdb_id: int,
        media_type: str,
        title: str,
        enrichment_data: dict,
        success: bool = True
    ):
        """Log an enrichment attempt.

        Args:
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.
            title: Media title.
            enrichment_data: AI enrichment data.
            success: Whether enrichment succeeded.
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO enrichment_log
                   (tmdb_id, media_type, title, enriched_at, enrichment_data, success)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tmdb_id, media_type, title, time.time(), json.dumps(enrichment_data), success),
            )

    def get_enrichment_log(self, limit: int = 50) -> List[dict]:
        """Get recent enrichment log entries.

        Args:
            limit: Maximum number of entries.

        Returns:
            list of dicts with enrichment info.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM enrichment_log ORDER BY enriched_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

    # ==================== Duplicate Detection ====================

    def check_duplicate(self, tmdb_id: int, media_type: str) -> Optional[dict]:
        """Check if a media item already exists in the destination.

        Args:
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.

        Returns:
            dict or None: Existing entry if found.
        """
        return self.get_by_tmdb_id(tmdb_id, media_type)

    def should_process(self, tmdb_id: int, media_type: str, quality_score: int) -> tuple:
        """Determine if a file should be processed (new or upgrade).

        Args:
            tmdb_id: TMDb ID.
            media_type: 'movie' or 'tv'.
            quality_score: Quality score of new file.

        Returns:
            tuple: (should_process: bool, reason: str, existing: dict or None)
        """
        existing = self.check_duplicate(tmdb_id, media_type)

        if not existing:
            return (True, "new", None)

        existing_quality = existing.get("quality_score", 0)

        if quality_score > existing_quality:
            return (True, "upgrade", existing)

        return (False, "duplicate", existing)

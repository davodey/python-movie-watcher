"""SQLite database for tracking processed movies."""

import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)


class ProcessedDatabase:
    """Tracks which movies have been processed to prevent duplicates."""

    def __init__(self, db_path):
        self.db_path = db_path
        self._ensure_directory()
        self._init_db()

    def _ensure_directory(self):
        """Create the database directory if it doesn't exist."""
        db_dir = os.path.dirname(self.db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _init_db(self):
        """Initialize the database schema."""
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS processed (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_path TEXT NOT NULL,
                    dest_path TEXT,
                    title TEXT,
                    year INTEGER,
                    tmdb_id INTEGER,
                    processed_at REAL NOT NULL,
                    status TEXT DEFAULT 'success'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_source_path
                ON processed(source_path)
            """)

    def _connect(self):
        """Create a database connection."""
        return sqlite3.connect(self.db_path)

    def is_processed(self, source_path):
        """Check if a file/folder has already been processed.

        Args:
            source_path: Original source path of the movie.

        Returns:
            bool: True if already processed.
        """
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM processed WHERE source_path = ? AND status = 'success'",
                (source_path,),
            )
            count = cursor.fetchone()[0]
            return count > 0

    def mark_processed(self, source_path, dest_path=None, title=None, year=None,
                       tmdb_id=None, status="success"):
        """Record a movie as processed.

        Args:
            source_path: Original source path.
            dest_path: Destination path after organization.
            title: Movie title.
            year: Release year.
            tmdb_id: TMDb movie ID.
            status: Processing status ('success' or 'failed').
        """
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO processed (source_path, dest_path, title, year, tmdb_id,
                   processed_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (source_path, dest_path, title, year, tmdb_id, time.time(), status),
            )
        logger.info("Recorded processed: %s (%s)", source_path, status)

    def get_recent(self, limit=20):
        """Get recently processed entries.

        Args:
            limit: Maximum number of entries to return.

        Returns:
            list of dicts with processing info.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM processed ORDER BY processed_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cursor.fetchall()]

"""
Media Sanitizer with Complete TMDb Metadata & n8n AI Enrichment.

A comprehensive media organization solution that:
- Monitors download directories for new movies and TV shows
- Fetches COMPLETE metadata from TMDb (credits, keywords, images, collections)
- Enriches metadata with AI via n8n webhook integration
- Creates Jellyfin-compatible NFO files with AI-generated descriptions
- Organizes files into clean folder structures
- Tracks processed files and collections in SQLite
"""

__version__ = "2.0.0"
__author__ = "Media Sanitizer Team"

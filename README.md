# Media Sanitizer

Comprehensive media organization with **complete TMDb metadata** and **n8n AI enrichment**.

Transform torrent downloads into perfectly organized, AI-enriched Jellyfin library entries.

## Features

- **Complete TMDb Metadata**: Fetches ALL metadata in single API calls including credits, keywords, images, collections, trailers, and more
- **n8n AI Enrichment**: Sends metadata to n8n webhook for OpenAI-powered content analysis
- **Family-Friendly Descriptions**: AI-generated descriptions tailored for family viewing
- **Content Warnings**: Automatic violence, language, and maturity ratings
- **Collection Tracking**: Tracks movie collections (MCU, Star Wars, etc.) for playlist generation
- **Quality-Based Upgrades**: Automatically replaces lower quality versions with upgrades
- **Movies + TV Shows**: Full support for both media types

## What It Does

1. **Watches** download directories for new movies and TV shows
2. **Parses** torrent filenames (title, year, quality, source)
3. **Fetches** COMPLETE TMDb metadata (cast, keywords, images, collections, trailers)
4. **Enriches** with AI via n8n webhook (content warnings, age recommendations, tags)
5. **Creates** Jellyfin/Kodi/Emby compatible NFO files with all metadata
6. **Downloads** high-quality poster and backdrop artwork
7. **Organizes** into clean folder structure
8. **Tracks** in SQLite to prevent re-processing

### Before
```
/torrents/complete/movies/
  The.Avengers.2012.1080p.BluRay.x264-SPARKS.mkv
```

### After
```
/media/movies/
  The Avengers (2012)/
    The Avengers (2012) [1080p Bluray].mkv
    The Avengers (2012).nfo           # Full metadata + AI content warnings
    poster.jpg
    fanart.jpg
```

## Quick Start

```bash
# 1. Clone and install
git clone https://github.com/davodey/python-movie-watcher.git
cd python-movie-watcher
./install.sh

# 2. Edit configuration
nano sanitizer_config.json

# 3. Run
python3 -m jellyfin_organizer.sanitizer_main -c sanitizer_config.json
```

## Requirements

- **Python 3.10+**
- **requests** library
- **TMDb API key** (free at https://www.themoviedb.org/settings/api)
- **n8n** (optional, for AI enrichment at http://localhost:5678)

## Configuration

Edit `sanitizer_config.json`:

```json
{
  "tmdb_api_key": "YOUR_TMDB_API_KEY",
  "n8n_webhook_url": "http://localhost:5678/webhook/enrich-metadata",

  "watch_folders": {
    "movies": "/mnt/media/torrents/complete/movies",
    "tv": "/mnt/media/torrents/complete/tv"
  },

  "output_folders": {
    "movies": "/mnt/media/sanatize/movies",
    "tv": "/mnt/media/sanatize/tv"
  },

  "watch_interval": 60,
  "min_file_size_mb": 100
}
```

## Usage

### Run as Service (Recommended)

```bash
# Install systemd service
sudo cp media-sanitizer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable media-sanitizer
sudo systemctl start media-sanitizer

# View logs
sudo journalctl -u media-sanitizer -f
```

### Run Manually

```bash
# Continuous monitoring
python3 -m jellyfin_organizer.sanitizer_main

# Process existing files
python3 -m jellyfin_organizer.sanitizer_main --scan-existing

# Process single file
python3 -m jellyfin_organizer.sanitizer_main --process /path/to/movie.mkv

# Show statistics
python3 -m jellyfin_organizer.sanitizer_main --stats

# Retry failed entries
python3 -m jellyfin_organizer.sanitizer_main --retry-failed
```

## TMDb Metadata (COMPLETE)

Fetches ALL metadata in single API calls using `append_to_response`:

- **Basic**: Title, year, overview, tagline, runtime, budget, revenue
- **Certification**: MPAA rating (G, PG, PG-13, R, etc.)
- **Collection**: Movie collection info (e.g., "The Avengers Collection")
- **Cast**: Top 10 actors with character names and photos
- **Crew**: Director, writer, composer
- **Keywords**: All TMDb keywords for filtering
- **Images**: Best poster, backdrop, and logo (by vote average)
- **Trailer**: YouTube trailer key
- **Similar**: Related movie/show IDs

## n8n AI Enrichment

When configured, sends metadata to n8n webhook which returns:

```json
{
  "success": true,
  "family_description": "AI-rewritten family-friendly description",
  "content_warnings": {
    "violence": "Moderate: Stylized action sequences",
    "language": "Mild: Infrequent mild profanity",
    "scary_content": "Mild: Intense action scenes",
    "mature_themes": "None"
  },
  "age_recommendation": "Ages 10+",
  "custom_tags": ["superhero", "action-packed", "team-up"],
  "similar_titles": ["Iron Man", "Captain America"]
}
```

## NFO Files

Generated NFO files include:

- All TMDb metadata (title, year, plot, ratings, genres, cast, crew)
- AI content warnings as tags for Jellyfin filtering
- Age recommendations
- Collection information
- Keywords and custom tags
- Poster, backdrop, and fanart URLs
- YouTube trailer links
- Similar title suggestions

## Database Schema

SQLite database tracks:

- **processed_files**: Files processed with TMDb IDs and quality scores
- **metadata_cache**: Cached TMDb responses (24-hour expiry)
- **collections**: Movie collection membership for playlists
- **enrichment_log**: AI enrichment history

## Quality Scoring

Automatically scores and compares quality:

| Source | Score | Resolution | Score | HDR | Bonus |
|--------|-------|------------|-------|-----|-------|
| REMUX | 100 | 2160p/4K | 40 | Dolby Vision | 15 |
| BluRay | 90 | 1080p | 30 | HDR10+ | 12 |
| WEB-DL | 75 | 720p | 20 | HDR10 | 10 |
| HDTV | 60 | 480p | 10 | HDR | 8 |

## Project Structure

```
python-movie-watcher/
  jellyfin_organizer/
    __init__.py           - Package init
    sanitizer_main.py     - Main orchestrator with AI enrichment
    tmdb.py               - Complete TMDb API client
    enricher.py           - n8n webhook integration
    metadata.py           - NFO file generation with AI data
    parser.py             - Filename parsing with quality scoring
    database.py           - SQLite with cache and collections
    watcher.py            - Directory monitoring
    organizer.py          - File organization
    artwork.py            - Image downloading
    config.py             - Configuration loading
  sanitizer_config.json   - Configuration file
  install.sh              - Installation script
  media-sanitizer.service - systemd service
  requirements.txt        - Python dependencies
```

## Logs

```
2026-01-31 19:30:00 [INFO] Starting media sanitizer...
2026-01-31 19:30:05 [INFO] Found new file: The.Avengers.2012.1080p.BluRay.mkv
2026-01-31 19:30:06 [INFO] TMDb match: The Avengers (2012) [ID: 24428]
2026-01-31 19:30:07 [INFO] Metadata: cast=10, keywords=25, collection=The Avengers Collection
2026-01-31 19:30:08 [INFO] Sending to n8n for AI enrichment...
2026-01-31 19:30:15 [INFO] AI enrichment complete (age: 10+, tags: 4)
2026-01-31 19:30:16 [INFO] Created NFO: The Avengers (2012).nfo
2026-01-31 19:30:18 [SUCCESS] Processed: The Avengers (2012)
```

## License

MIT

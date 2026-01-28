# Jellyfin Auto-Organizer

Automatically transforms torrent movie downloads into perfectly organized Jellyfin library entries with complete metadata, artwork, and zero manual intervention.

## What It Does

1. **Watches** a download directory for new movie files/folders
2. **Parses** torrent filenames to extract the movie title and year
3. **Fetches** complete metadata from TMDb (The Movie Database)
4. **Moves** the video file into an organized library structure
5. **Creates** Jellyfin/Kodi/Emby compatible NFO metadata files
6. **Downloads** poster and backdrop artwork

### Before
```
/torrents/complete/movies/
  Movie.Name.2024.1080p.WEB-DL.x264-GROUP.mkv
```

### After
```
/media/movies/
  Movie.Name.2024.1080p.WEB-DL.x264-GROUP/
    Movie Name.2024.mkv
    Movie Name.2024.nfo
    poster.jpg
    backdrop.jpg
```

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/davodey/python-movie-watcher.git
cd python-movie-watcher

# 2. Run setup (creates config, installs dependencies)
./setup.sh

# 3. Install as a system service
sudo ./install_service.sh

# 4. Start the service
sudo systemctl start jellyfin-organizer
```

## Requirements

- Python 3.7+
- `requests` library (installed by setup.sh)
- TMDb API key (free at https://www.themoviedb.org/settings/api)

## Configuration

Configuration is stored in `config.json`. Created automatically by `setup.sh`, or copy from `config.json.example`.

| Setting | Default | Description |
|---------|---------|-------------|
| `tmdb_api_key` | - | Your TMDb API key (required) |
| `watch_directory` | `/media/david/MEDIA/torrents/complete/movies` | Directory to monitor for new downloads |
| `destination_directory` | `/media/david/MEDIA/media/movies` | Organized library output directory |
| `settle_time` | `30` | Seconds to wait for downloads to complete |
| `min_file_size_mb` | `100` | Minimum file size to process (filters samples) |
| `scan_interval` | `60` | Seconds between directory scans |
| `log_file` | `/var/log/jellyfin_organizer.log` | Log file path |
| `database_file` | `/var/lib/jellyfin_organizer/processed.db` | SQLite database path |
| `video_extensions` | `.mkv,.mp4,.avi,...` | Video file extensions to recognize |
| `subtitle_extensions` | `.srt,.sub,.ass,...` | Subtitle extensions to preserve |

## Usage

### As a Service (recommended)

```bash
sudo systemctl start jellyfin-organizer    # Start
sudo systemctl stop jellyfin-organizer     # Stop
sudo systemctl status jellyfin-organizer   # Status
sudo journalctl -u jellyfin-organizer -f   # Follow logs
```

### Manual Run

```bash
# Run in service mode (continuous monitoring)
python3 -m jellyfin_organizer.main

# Process a single file or folder
python3 -m jellyfin_organizer.main --process /path/to/movie.mkv

# Process all existing files on startup
python3 -m jellyfin_organizer.main --scan-existing

# Use a specific config file
python3 -m jellyfin_organizer.main -c /path/to/config.json
```

## Project Structure

```
python-movie-watcher/
  jellyfin_organizer/
    __init__.py       - Package init
    __main__.py       - Module entry point
    main.py           - Service orchestration and CLI
    config.py         - Configuration loading
    parser.py         - Torrent filename parsing
    tmdb.py           - TMDb API client
    metadata.py       - NFO XML file generation
    artwork.py        - Poster/backdrop downloading
    organizer.py      - File moving and organization
    database.py       - SQLite processed file tracking
    watcher.py        - Directory monitoring
  config.json.example - Example configuration
  setup.sh            - Interactive setup script
  install_service.sh  - systemd service installer
  requirements.txt    - Python dependencies
```

## NFO Metadata

Generated NFO files are compatible with Jellyfin, Kodi, and Emby. They include:

- Title, original title, year, release date, runtime
- TMDb rating with vote count
- Plot summary and tagline
- TMDb and IMDb IDs
- Genres, studios, production countries
- Full cast (top 15) with character names and photo URLs
- Directors and writers
- YouTube trailer link

## Filename Parsing

The parser strips common torrent artifacts from filenames:

- Resolution: `1080p`, `2160p`, `720p`, `4K`, `UHD`
- Source: `WEB-DL`, `BluRay`, `WEBRip`, `HDTV`, `REMUX`
- Codec: `x264`, `x265`, `HEVC`, `AV1`, `10bit`
- Audio: `AAC`, `DTS`, `TrueHD`, `Atmos`, `5.1`, `7.1`
- Release groups: `YTS.MX`, `RARBG`, `Tigole`, etc.
- Bracketed tags: `[UNCUT]`, `[REMASTERED]`, etc.
- Website tags: `www.site.org`

## Safety Features

- **Atomic operations**: Files are fully organized or rolled back on failure
- **No re-encoding**: Original video files are never modified
- **Duplicate prevention**: SQLite database tracks processed files
- **Stability check**: Waits for downloads to finish before processing
- **Size filter**: Ignores sample files under 100MB
- **Auto-restart**: systemd restarts the service on crash
- **Rate limiting**: Respects TMDb API limits

## Logs

```bash
# View log file
tail -f /var/log/jellyfin_organizer.log

# View systemd journal
sudo journalctl -u jellyfin-organizer -f
```

## License

MIT

"""TMDb (The Movie Database) API client."""

import logging
import time

import requests

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# Rate limiting: TMDb allows ~40 requests per 10 seconds
REQUEST_INTERVAL = 0.25  # seconds between requests


class TMDbClient:
    """Client for The Movie Database API."""

    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()
        self.session.params = {"api_key": self.api_key}
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint, params=None):
        """Make a GET request to TMDb API.

        Args:
            endpoint: API endpoint path (e.g. '/search/movie').
            params: Additional query parameters.

        Returns:
            dict: JSON response data.

        Raises:
            requests.RequestException: On network/API errors.
        """
        self._rate_limit()
        url = f"{TMDB_BASE_URL}{endpoint}"
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def search_movie(self, title, year=None):
        """Search for a movie by title and optional year.

        Args:
            title: Movie title to search for.
            year: Optional release year to narrow results.

        Returns:
            dict or None: Best matching movie result, or None if no match.
        """
        params = {"query": title}
        if year:
            params["year"] = year

        data = self._get("/search/movie", params)

        if data.get("results"):
            return data["results"][0]

        # Retry without year if no results
        if year:
            logger.info("No results with year %d, retrying without year", year)
            params.pop("year")
            data = self._get("/search/movie", params)
            if data.get("results"):
                return data["results"][0]

        return None

    def get_movie_details(self, movie_id):
        """Get full movie details including credits and videos.

        Args:
            movie_id: TMDb movie ID.

        Returns:
            dict: Complete movie details with credits and videos.
        """
        data = self._get(
            f"/movie/{movie_id}",
            params={"append_to_response": "credits,videos,external_ids"},
        )
        return data

    def get_full_movie_info(self, title, year=None):
        """Search for a movie and return complete metadata.

        Args:
            title: Movie title to search for.
            year: Optional release year.

        Returns:
            dict or None: Complete movie metadata, or None if no match found.
        """
        search_result = self.search_movie(title, year)
        if not search_result:
            logger.warning("No TMDb match found for: %s (%s)", title, year)
            return None

        movie_id = search_result["id"]
        details = self.get_movie_details(movie_id)

        return self._format_movie_data(details)

    def _format_movie_data(self, details):
        """Format raw TMDb API data into organized metadata dict.

        Args:
            details: Raw TMDb movie details response.

        Returns:
            dict: Formatted movie metadata.
        """
        # Extract credits
        credits = details.get("credits", {})
        cast = []
        for i, actor in enumerate(credits.get("cast", [])[:15]):
            cast.append({
                "name": actor.get("name", ""),
                "role": actor.get("character", ""),
                "order": i,
                "thumb": (
                    f"{TMDB_IMAGE_BASE}/original{actor['profile_path']}"
                    if actor.get("profile_path")
                    else ""
                ),
            })

        crew = credits.get("crew", [])
        directors = [p["name"] for p in crew if p.get("job") == "Director"]
        writers = [
            p["name"]
            for p in crew
            if p.get("job") in ("Screenplay", "Writer", "Story")
        ]

        # Extract trailer
        trailer_url = ""
        videos = details.get("videos", {}).get("results", [])
        for video in videos:
            if video.get("type") == "Trailer" and video.get("site") == "YouTube":
                trailer_url = f"https://www.youtube.com/watch?v={video['key']}"
                break

        # External IDs
        external_ids = details.get("external_ids", {})
        imdb_id = external_ids.get("imdb_id", "") or details.get("imdb_id", "")

        # Image URLs
        poster_url = (
            f"{TMDB_IMAGE_BASE}/original{details['poster_path']}"
            if details.get("poster_path")
            else ""
        )
        backdrop_url = (
            f"{TMDB_IMAGE_BASE}/original{details['backdrop_path']}"
            if details.get("backdrop_path")
            else ""
        )

        release_date = details.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

        return {
            "title": details.get("title", ""),
            "original_title": details.get("original_title", ""),
            "year": year,
            "premiered": release_date,
            "runtime": details.get("runtime"),
            "plot": details.get("overview", ""),
            "tagline": details.get("tagline", ""),
            "tmdb_id": details.get("id"),
            "imdb_id": imdb_id,
            "rating": details.get("vote_average"),
            "votes": details.get("vote_count"),
            "genres": [g["name"] for g in details.get("genres", [])],
            "studios": [s["name"] for s in details.get("production_companies", [])],
            "countries": [
                c["name"] for c in details.get("production_countries", [])
            ],
            "cast": cast,
            "directors": directors,
            "writers": writers,
            "trailer": trailer_url,
            "poster_url": poster_url,
            "backdrop_url": backdrop_url,
        }

    # -------------------------------------------------------------------------
    # TV Show Methods
    # -------------------------------------------------------------------------

    def search_tv(self, title, year=None):
        """Search for a TV show by title and optional first air year.

        Args:
            title: TV show title to search for.
            year: Optional first air year to narrow results.

        Returns:
            dict or None: Best matching TV show result, or None if no match.
        """
        params = {"query": title}
        if year:
            params["first_air_date_year"] = year

        data = self._get("/search/tv", params)

        if data.get("results"):
            return data["results"][0]

        # Retry without year if no results
        if year:
            logger.info("No TV results with year %d, retrying without year", year)
            params.pop("first_air_date_year")
            data = self._get("/search/tv", params)
            if data.get("results"):
                return data["results"][0]

        return None

    def get_tv_details(self, tv_id):
        """Get full TV show details including credits and external IDs.

        Args:
            tv_id: TMDb TV show ID.

        Returns:
            dict: Complete TV show details.
        """
        data = self._get(
            f"/tv/{tv_id}",
            params={"append_to_response": "credits,external_ids,content_ratings"},
        )
        return data

    def get_tv_season(self, tv_id, season_number):
        """Get TV season details including all episodes.

        Args:
            tv_id: TMDb TV show ID.
            season_number: Season number.

        Returns:
            dict: Season details with episodes.
        """
        data = self._get(
            f"/tv/{tv_id}/season/{season_number}",
            params={"append_to_response": "credits"},
        )
        return data

    def get_tv_episode(self, tv_id, season_number, episode_number):
        """Get TV episode details.

        Args:
            tv_id: TMDb TV show ID.
            season_number: Season number.
            episode_number: Episode number.

        Returns:
            dict: Episode details.
        """
        data = self._get(
            f"/tv/{tv_id}/season/{season_number}/episode/{episode_number}",
            params={"append_to_response": "credits"},
        )
        return data

    def get_full_tv_info(self, title, year=None):
        """Search for a TV show and return complete metadata.

        Args:
            title: TV show title to search for.
            year: Optional first air year.

        Returns:
            dict or None: Complete TV show metadata, or None if no match found.
        """
        search_result = self.search_tv(title, year)
        if not search_result:
            logger.warning("No TMDb TV match found for: %s (%s)", title, year)
            return None

        tv_id = search_result["id"]
        details = self.get_tv_details(tv_id)

        return self._format_tv_data(details)

    def get_full_episode_info(self, tv_id, season_number, episode_number):
        """Get complete episode metadata.

        Args:
            tv_id: TMDb TV show ID.
            season_number: Season number.
            episode_number: Episode number.

        Returns:
            dict or None: Complete episode metadata.
        """
        try:
            episode = self.get_tv_episode(tv_id, season_number, episode_number)
            return self._format_episode_data(episode, tv_id)
        except requests.RequestException:
            logger.warning("Failed to fetch episode S%02dE%02d for TV ID %d",
                          season_number, episode_number, tv_id)
            return None

    def _format_tv_data(self, details):
        """Format raw TMDb TV API data into organized metadata dict.

        Args:
            details: Raw TMDb TV show details response.

        Returns:
            dict: Formatted TV show metadata.
        """
        # Extract credits
        credits = details.get("credits", {})
        cast = []
        for i, actor in enumerate(credits.get("cast", [])[:15]):
            cast.append({
                "name": actor.get("name", ""),
                "role": actor.get("character", ""),
                "order": i,
                "thumb": (
                    f"{TMDB_IMAGE_BASE}/original{actor['profile_path']}"
                    if actor.get("profile_path")
                    else ""
                ),
            })

        crew = credits.get("crew", [])
        creators = [c["name"] for c in details.get("created_by", [])]

        # External IDs
        external_ids = details.get("external_ids", {})
        imdb_id = external_ids.get("imdb_id", "")
        tvdb_id = external_ids.get("tvdb_id")

        # Image URLs
        poster_url = (
            f"{TMDB_IMAGE_BASE}/original{details['poster_path']}"
            if details.get("poster_path")
            else ""
        )
        backdrop_url = (
            f"{TMDB_IMAGE_BASE}/original{details['backdrop_path']}"
            if details.get("backdrop_path")
            else ""
        )

        first_air_date = details.get("first_air_date", "")
        year = int(first_air_date[:4]) if first_air_date and len(first_air_date) >= 4 else None

        # Content rating (US)
        content_rating = ""
        ratings = details.get("content_ratings", {}).get("results", [])
        for r in ratings:
            if r.get("iso_3166_1") == "US":
                content_rating = r.get("rating", "")
                break

        return {
            "title": details.get("name", ""),
            "original_title": details.get("original_name", ""),
            "year": year,
            "premiered": first_air_date,
            "status": details.get("status", ""),
            "plot": details.get("overview", ""),
            "tagline": details.get("tagline", ""),
            "tmdb_id": details.get("id"),
            "imdb_id": imdb_id,
            "tvdb_id": tvdb_id,
            "rating": details.get("vote_average"),
            "votes": details.get("vote_count"),
            "mpaa": content_rating,
            "genres": [g["name"] for g in details.get("genres", [])],
            "studios": [n["name"] for n in details.get("networks", [])],
            "cast": cast,
            "creators": creators,
            "seasons": details.get("number_of_seasons"),
            "episodes": details.get("number_of_episodes"),
            "poster_url": poster_url,
            "backdrop_url": backdrop_url,
        }

    def _format_episode_data(self, episode, tv_id):
        """Format raw TMDb episode data into organized metadata dict.

        Args:
            episode: Raw TMDb episode details response.
            tv_id: TMDb TV show ID.

        Returns:
            dict: Formatted episode metadata.
        """
        # Extract credits
        credits = episode.get("credits", {})
        guest_stars = []
        for i, actor in enumerate(episode.get("guest_stars", [])[:10]):
            guest_stars.append({
                "name": actor.get("name", ""),
                "role": actor.get("character", ""),
                "order": i,
                "thumb": (
                    f"{TMDB_IMAGE_BASE}/original{actor['profile_path']}"
                    if actor.get("profile_path")
                    else ""
                ),
            })

        crew = credits.get("crew", [])
        directors = [p["name"] for p in crew if p.get("job") == "Director"]
        writers = [
            p["name"]
            for p in crew
            if p.get("job") in ("Writer", "Story", "Teleplay")
        ]

        # Episode still image
        still_url = (
            f"{TMDB_IMAGE_BASE}/original{episode['still_path']}"
            if episode.get("still_path")
            else ""
        )

        return {
            "title": episode.get("name", ""),
            "season": episode.get("season_number"),
            "episode": episode.get("episode_number"),
            "aired": episode.get("air_date", ""),
            "runtime": episode.get("runtime"),
            "plot": episode.get("overview", ""),
            "rating": episode.get("vote_average"),
            "votes": episode.get("vote_count"),
            "tmdb_id": episode.get("id"),
            "tv_tmdb_id": tv_id,
            "directors": directors,
            "writers": writers,
            "guest_stars": guest_stars,
            "still_url": still_url,
        }

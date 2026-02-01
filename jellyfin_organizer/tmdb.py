"""TMDb (The Movie Database) API client with COMPLETE metadata fetching."""

import json
import logging
import time
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)

TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p"

# Rate limiting: TMDb allows ~40 requests per 10 seconds
REQUEST_INTERVAL = 0.25  # seconds between requests


class TMDbClient:
    """Client for The Movie Database API with comprehensive metadata fetching.

    Fetches ALL available metadata in single API calls using append_to_response,
    including: credits, keywords, images, similar, recommendations, release_dates,
    videos, and collection info.
    """

    def __init__(self, api_key: str, image_base_url: str = None, language: str = "en-US"):
        """Initialize TMDb client.

        Args:
            api_key: TMDb API key.
            image_base_url: Base URL for images (default: original quality).
            language: Language for API responses.
        """
        self.api_key = api_key
        self.image_base_url = image_base_url or f"{TMDB_IMAGE_BASE}/original"
        self.language = language
        self.session = requests.Session()
        self.session.params = {"api_key": self.api_key, "language": self.language}
        self._last_request_time = 0

    def _rate_limit(self):
        """Enforce rate limiting between API calls."""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_INTERVAL:
            time.sleep(REQUEST_INTERVAL - elapsed)
        self._last_request_time = time.time()

    def _get(self, endpoint: str, params: dict = None) -> dict:
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

    # ==================== Movie Methods ====================

    def search_movie(self, title: str, year: int = None) -> Optional[dict]:
        """Search for a movie by title and optional year.

        Args:
            title: Movie title to search for.
            year: Optional release year to narrow results.

        Returns:
            dict or None: Best matching movie result, or None if no match.
        """
        params = {"query": title, "include_adult": "false"}
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

    def get_complete_movie_data(self, movie_id: int) -> dict:
        """Get COMPLETE movie details in a SINGLE API call.

        Uses append_to_response to fetch:
        - credits (cast, crew)
        - keywords
        - images (posters, backdrops, logos)
        - similar movies
        - recommendations
        - release_dates (for certifications)
        - videos (trailers)
        - external_ids (IMDb, etc.)

        Args:
            movie_id: TMDb movie ID.

        Returns:
            dict: Complete movie details with all appended data.
        """
        append_to = ",".join([
            "credits",
            "keywords",
            "images",
            "similar",
            "recommendations",
            "release_dates",
            "videos",
            "external_ids"
        ])

        data = self._get(
            f"/movie/{movie_id}",
            params={"append_to_response": append_to}
        )
        return data

    def get_full_movie_info(self, title: str, year: int = None) -> Optional[dict]:
        """Search for a movie and return COMPLETE metadata.

        Args:
            title: Movie title to search for.
            year: Optional release year.

        Returns:
            dict or None: Complete formatted movie metadata, or None if no match.
        """
        search_result = self.search_movie(title, year)
        if not search_result:
            logger.warning("No TMDb match found for: %s (%s)", title, year)
            return None

        movie_id = search_result["id"]
        details = self.get_complete_movie_data(movie_id)

        return self._format_complete_movie_data(details)

    def _format_complete_movie_data(self, details: dict) -> dict:
        """Format raw TMDb API data into comprehensive metadata dict.

        Args:
            details: Raw TMDb movie details response with appended data.

        Returns:
            dict: Fully formatted movie metadata.
        """
        # Extract release date and year
        release_date = details.get("release_date", "")
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 else None

        # Extract credits
        credits = details.get("credits", {})
        cast = self._extract_cast(credits.get("cast", []), limit=10)
        crew_data = self._extract_crew(credits.get("crew", []))

        # Extract certification (US MPAA rating)
        certification = self._extract_us_certification(details.get("release_dates", {}))

        # Extract collection info
        collection = self._extract_collection(details.get("belongs_to_collection"))

        # Extract keywords
        keywords = [kw["name"] for kw in details.get("keywords", {}).get("keywords", [])]

        # Extract best images
        images = self._extract_best_images(details.get("images", {}), details)

        # Extract trailer
        trailer_key = self._extract_trailer_key(details.get("videos", {}))

        # Extract similar/recommended movie IDs
        similar_ids = [m["id"] for m in details.get("similar", {}).get("results", [])[:10]]
        recommended_ids = [m["id"] for m in details.get("recommendations", {}).get("results", [])[:10]]

        # Extract external IDs
        external_ids = details.get("external_ids", {})
        imdb_id = external_ids.get("imdb_id", "") or details.get("imdb_id", "")

        # Production companies
        production_companies = [pc["name"] for pc in details.get("production_companies", [])]

        return {
            # Basic info
            "media_type": "movie",
            "title": details.get("title", ""),
            "original_title": details.get("original_title", ""),
            "year": year,
            "tmdb_id": details.get("id"),
            "imdb_id": imdb_id,
            "description": details.get("overview", ""),
            "tagline": details.get("tagline", ""),
            "runtime": details.get("runtime"),
            "budget": details.get("budget"),
            "revenue": details.get("revenue"),
            "premiered": release_date,

            # Ratings and votes
            "tmdb_rating": details.get("vote_average"),
            "tmdb_votes": details.get("vote_count"),
            "rating": certification,  # MPAA rating (G, PG, PG-13, R, etc.)

            # Genres
            "genres": [g["name"] for g in details.get("genres", [])],

            # Collection
            "collection": collection,

            # Cast and crew
            "cast": cast,
            "crew": crew_data,

            # Keywords (important for filtering)
            "keywords": keywords,

            # Images (best quality selected)
            "images": images,

            # Trailer
            "trailer_key": trailer_key,

            # Similar/Recommended
            "similar_movies": similar_ids,
            "recommended_movies": recommended_ids,

            # Production
            "production_companies": production_companies,
            "studios": production_companies,  # Alias for compatibility
            "countries": [c["name"] for c in details.get("production_countries", [])],

            # Compatibility fields for existing code
            "plot": details.get("overview", ""),
            "poster_url": images.get("poster", ""),
            "backdrop_url": images.get("backdrop", ""),
        }

    def _extract_cast(self, cast_list: List[dict], limit: int = 10) -> List[dict]:
        """Extract top cast members with details."""
        result = []
        for i, actor in enumerate(cast_list[:limit]):
            result.append({
                "name": actor.get("name", ""),
                "character": actor.get("character", ""),
                "role": actor.get("character", ""),  # Alias
                "order": actor.get("order", i),
                "tmdb_id": actor.get("id"),
                "thumb": (
                    f"{self.image_base_url}{actor['profile_path']}"
                    if actor.get("profile_path") else ""
                ),
            })
        return result

    def _extract_crew(self, crew_list: List[dict]) -> dict:
        """Extract key crew members (director, writer, composer)."""
        result = {
            "director": None,
            "directors": [],
            "writer": None,
            "writers": [],
            "composer": None,
        }

        for person in crew_list:
            job = person.get("job", "")
            name = person.get("name", "")

            if job == "Director":
                result["directors"].append(name)
                if not result["director"]:
                    result["director"] = name
            elif job in ("Screenplay", "Writer", "Story"):
                if name not in result["writers"]:
                    result["writers"].append(name)
                if not result["writer"]:
                    result["writer"] = name
            elif job == "Original Music Composer":
                if not result["composer"]:
                    result["composer"] = name

        return result

    def _extract_us_certification(self, release_dates: dict) -> str:
        """Extract US MPAA certification from release_dates."""
        results = release_dates.get("results", [])

        # First try US
        for country in results:
            if country.get("iso_3166_1") == "US":
                for release in country.get("release_dates", []):
                    cert = release.get("certification", "")
                    if cert:
                        return cert

        # Fall back to any certification
        for country in results:
            for release in country.get("release_dates", []):
                cert = release.get("certification", "")
                if cert:
                    return cert

        return ""

    def _extract_collection(self, collection_data: Optional[dict]) -> Optional[dict]:
        """Extract collection info if movie belongs to one."""
        if not collection_data:
            return None

        return {
            "id": collection_data.get("id"),
            "name": collection_data.get("name", ""),
            "poster_path": (
                f"{self.image_base_url}{collection_data['poster_path']}"
                if collection_data.get("poster_path") else ""
            ),
            "backdrop_path": (
                f"{self.image_base_url}{collection_data['backdrop_path']}"
                if collection_data.get("backdrop_path") else ""
            ),
        }

    def _extract_best_images(self, images_data: dict, details: dict) -> dict:
        """Extract best quality images (highest vote_average)."""
        result = {
            "poster": "",
            "backdrop": "",
            "logo": "",
        }

        # Get best poster (by vote_average)
        posters = images_data.get("posters", [])
        if posters:
            # Filter English posters first, then sort by vote_average
            english_posters = [p for p in posters if p.get("iso_639_1") in ("en", None)]
            if english_posters:
                best = max(english_posters, key=lambda x: x.get("vote_average", 0))
            else:
                best = max(posters, key=lambda x: x.get("vote_average", 0))
            result["poster"] = f"{self.image_base_url}{best['file_path']}"
        elif details.get("poster_path"):
            result["poster"] = f"{self.image_base_url}{details['poster_path']}"

        # Get best backdrop
        backdrops = images_data.get("backdrops", [])
        if backdrops:
            best = max(backdrops, key=lambda x: x.get("vote_average", 0))
            result["backdrop"] = f"{self.image_base_url}{best['file_path']}"
        elif details.get("backdrop_path"):
            result["backdrop"] = f"{self.image_base_url}{details['backdrop_path']}"

        # Get logo if available
        logos = images_data.get("logos", [])
        if logos:
            english_logos = [l for l in logos if l.get("iso_639_1") in ("en", None)]
            if english_logos:
                best = max(english_logos, key=lambda x: x.get("vote_average", 0))
                result["logo"] = f"{self.image_base_url}{best['file_path']}"

        return result

    def _extract_trailer_key(self, videos_data: dict) -> str:
        """Extract YouTube trailer key."""
        results = videos_data.get("results", [])

        # Look for official trailer on YouTube
        for video in results:
            if (video.get("type") == "Trailer" and
                video.get("site") == "YouTube" and
                video.get("official", True)):
                return video.get("key", "")

        # Fall back to any YouTube trailer
        for video in results:
            if video.get("type") == "Trailer" and video.get("site") == "YouTube":
                return video.get("key", "")

        # Fall back to any YouTube video
        for video in results:
            if video.get("site") == "YouTube":
                return video.get("key", "")

        return ""

    # ==================== TV Show Methods ====================

    def search_tv(self, show_name: str, year: int = None) -> Optional[dict]:
        """Search for a TV show by name.

        Args:
            show_name: TV show name to search for.
            year: Optional first air year.

        Returns:
            dict or None: Best matching TV show result, or None if no match.
        """
        params = {"query": show_name}
        if year:
            params["first_air_date_year"] = year

        data = self._get("/search/tv", params)

        if data.get("results"):
            return data["results"][0]

        # Retry without year
        if year:
            params.pop("first_air_date_year")
            data = self._get("/search/tv", params)
            if data.get("results"):
                return data["results"][0]

        return None

    def get_complete_tv_data(self, tv_id: int) -> dict:
        """Get COMPLETE TV show details in a SINGLE API call.

        Args:
            tv_id: TMDb TV show ID.

        Returns:
            dict: Complete TV show details with all appended data.
        """
        append_to = ",".join([
            "credits",
            "keywords",
            "images",
            "similar",
            "recommendations",
            "content_ratings",
            "videos",
            "external_ids"
        ])

        data = self._get(
            f"/tv/{tv_id}",
            params={"append_to_response": append_to}
        )
        return data

    def get_tv_episode_details(self, tv_id: int, season: int, episode: int) -> Optional[dict]:
        """Get details for a specific episode.

        Args:
            tv_id: TMDb TV show ID.
            season: Season number.
            episode: Episode number.

        Returns:
            dict or None: Episode details, or None if not found.
        """
        try:
            data = self._get(
                f"/tv/{tv_id}/season/{season}/episode/{episode}",
                params={"append_to_response": "credits,images"}
            )
            return data
        except Exception:
            return None

    def get_full_tv_info(self, show_name: str, year: int = None) -> Optional[dict]:
        """Search for a TV show and return COMPLETE metadata.

        Args:
            show_name: TV show name to search for.
            year: Optional first air year.

        Returns:
            dict or None: Complete TV show metadata, or None if no match.
        """
        search_result = self.search_tv(show_name, year)
        if not search_result:
            logger.warning("No TMDb TV match found for: %s", show_name)
            return None

        tv_id = search_result["id"]
        details = self.get_complete_tv_data(tv_id)

        return self._format_complete_tv_data(details)

    def get_full_episode_info(self, tv_id: int, season: int, episode: int) -> Optional[dict]:
        """Get complete episode metadata.

        Args:
            tv_id: TMDb TV show ID.
            season: Season number.
            episode: Episode number.

        Returns:
            dict or None: Formatted episode metadata.
        """
        ep_data = self.get_tv_episode_details(tv_id, season, episode)
        if not ep_data:
            return None

        return self._format_episode_data(ep_data, season, episode)

    def _format_complete_tv_data(self, details: dict) -> dict:
        """Format raw TMDb TV API data into comprehensive metadata dict."""
        first_air_date = details.get("first_air_date", "")
        year = int(first_air_date[:4]) if first_air_date and len(first_air_date) >= 4 else None

        # Extract credits
        credits = details.get("credits", {})
        cast = self._extract_cast(credits.get("cast", []), limit=10)

        # Created by
        creators = [c.get("name", "") for c in details.get("created_by", [])]

        # Extract certification
        content_rating = self._extract_tv_rating(details.get("content_ratings", {}))

        # Extract keywords
        keywords = [kw["name"] for kw in details.get("keywords", {}).get("results", [])]

        # Extract best images
        images = self._extract_best_images(details.get("images", {}), details)

        # Extract trailer
        trailer_key = self._extract_trailer_key(details.get("videos", {}))

        # Extract similar/recommended
        similar_ids = [s["id"] for s in details.get("similar", {}).get("results", [])[:10]]

        # External IDs
        external_ids = details.get("external_ids", {})

        # Networks
        networks = [n["name"] for n in details.get("networks", [])]

        return {
            "media_type": "tv",
            "title": details.get("name", ""),
            "original_title": details.get("original_name", ""),
            "show_name": details.get("name", ""),  # Alias
            "year": year,
            "tmdb_id": details.get("id"),
            "imdb_id": external_ids.get("imdb_id", ""),
            "tvdb_id": external_ids.get("tvdb_id"),
            "description": details.get("overview", ""),
            "tagline": details.get("tagline", ""),
            "premiered": first_air_date,
            "status": details.get("status", ""),

            # Episode/Season info
            "number_of_seasons": details.get("number_of_seasons"),
            "number_of_episodes": details.get("number_of_episodes"),

            # Ratings
            "tmdb_rating": details.get("vote_average"),
            "tmdb_votes": details.get("vote_count"),
            "rating": content_rating,

            # Genres
            "genres": [g["name"] for g in details.get("genres", [])],

            # Cast and creators
            "cast": cast,
            "creators": creators,

            # Keywords
            "keywords": keywords,

            # Images
            "images": images,
            "poster_url": images.get("poster", ""),
            "backdrop_url": images.get("backdrop", ""),

            # Trailer
            "trailer_key": trailer_key,

            # Similar shows
            "similar_shows": similar_ids,

            # Networks/Studios
            "networks": networks,
            "studios": networks,

            # Compatibility
            "plot": details.get("overview", ""),
        }

    def _extract_tv_rating(self, content_ratings: dict) -> str:
        """Extract US TV content rating."""
        results = content_ratings.get("results", [])

        for rating in results:
            if rating.get("iso_3166_1") == "US":
                return rating.get("rating", "")

        # Fall back to any rating
        if results:
            return results[0].get("rating", "")

        return ""

    def _format_episode_data(self, ep_data: dict, season: int, episode: int) -> dict:
        """Format episode data from TMDb."""
        credits = ep_data.get("credits", {})

        # Get guest stars
        guest_stars = []
        for star in ep_data.get("guest_stars", [])[:5]:
            guest_stars.append({
                "name": star.get("name", ""),
                "role": star.get("character", ""),
                "thumb": (
                    f"{self.image_base_url}{star['profile_path']}"
                    if star.get("profile_path") else ""
                ),
            })

        # Get directors and writers
        crew = credits.get("crew", [])
        directors = [p["name"] for p in crew if p.get("job") == "Director"]
        writers = [p["name"] for p in crew if p.get("job") in ("Writer", "Story")]

        # Get still image
        still_path = ep_data.get("still_path")
        still_url = f"{self.image_base_url}{still_path}" if still_path else ""

        return {
            "title": ep_data.get("name", ""),
            "episode_title": ep_data.get("name", ""),
            "season": season,
            "episode": episode,
            "tmdb_id": ep_data.get("id"),
            "plot": ep_data.get("overview", ""),
            "episode_plot": ep_data.get("overview", ""),
            "aired": ep_data.get("air_date", ""),
            "episode_air_date": ep_data.get("air_date", ""),
            "runtime": ep_data.get("runtime"),
            "rating": ep_data.get("vote_average"),
            "votes": ep_data.get("vote_count"),
            "directors": directors,
            "writers": writers,
            "guest_stars": guest_stars,
            "still_url": still_url,
        }

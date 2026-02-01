"""n8n Webhook Enricher - Sends metadata to n8n for AI enrichment via OpenAI."""

import json
import logging
import time
from typing import Dict, List, Optional, Any

import requests

logger = logging.getLogger(__name__)


class N8nEnricher:
    """Client for n8n webhook that enriches metadata with OpenAI via n8n workflow.

    Sends comprehensive TMDb metadata to n8n, which processes it through OpenAI
    to generate:
    - Family-friendly descriptions
    - Content warnings (violence, language, scary content, mature themes)
    - Age recommendations
    - Custom tags
    - Similar title suggestions
    """

    def __init__(
        self,
        webhook_url: str,
        timeout: int = 30,
        retry_count: int = 3,
        retry_delay: float = 2.0
    ):
        """Initialize n8n enricher.

        Args:
            webhook_url: n8n webhook URL (e.g., http://localhost:5678/webhook/enrich-metadata)
            timeout: Request timeout in seconds.
            retry_count: Number of retry attempts on failure.
            retry_delay: Delay between retries in seconds (doubles each retry).
        """
        self.webhook_url = webhook_url
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })

    def enrich_movie(self, movie_data: dict) -> Optional[dict]:
        """Send movie metadata to n8n for AI enrichment.

        Args:
            movie_data: Complete movie metadata from TMDb.

        Returns:
            dict or None: Enriched data with AI-generated content, or None on failure.
        """
        payload = self._build_movie_payload(movie_data)
        return self._send_with_retry(payload)

    def enrich_tv_show(self, tv_data: dict, episode_data: dict = None) -> Optional[dict]:
        """Send TV show metadata to n8n for AI enrichment.

        Args:
            tv_data: Complete TV show metadata from TMDb.
            episode_data: Optional episode-specific data.

        Returns:
            dict or None: Enriched data with AI-generated content, or None on failure.
        """
        payload = self._build_tv_payload(tv_data, episode_data)
        return self._send_with_retry(payload)

    def _build_movie_payload(self, movie_data: dict) -> dict:
        """Build the complete payload to send to n8n for movies.

        Args:
            movie_data: TMDb movie metadata.

        Returns:
            dict: Formatted payload for n8n webhook.
        """
        # Extract images dict or build from URLs
        images = movie_data.get("images", {})
        if not images:
            images = {
                "poster": movie_data.get("poster_url", ""),
                "backdrop": movie_data.get("backdrop_url", ""),
                "logo": "",
            }

        # Extract crew data
        crew = movie_data.get("crew", {})
        if isinstance(crew, dict):
            crew_formatted = {
                "director": crew.get("director") or (crew.get("directors", [None])[0] if crew.get("directors") else None),
                "writer": crew.get("writer") or (crew.get("writers", [None])[0] if crew.get("writers") else None),
                "composer": crew.get("composer"),
            }
        else:
            crew_formatted = {"director": None, "writer": None, "composer": None}

        return {
            "media_type": "movie",
            "title": movie_data.get("title", ""),
            "year": str(movie_data.get("year", "")),
            "tmdb_id": str(movie_data.get("tmdb_id", "")),
            "imdb_id": movie_data.get("imdb_id", ""),
            "description": movie_data.get("description", "") or movie_data.get("plot", ""),
            "tagline": movie_data.get("tagline", ""),
            "genres": ", ".join(movie_data.get("genres", [])),
            "rating": movie_data.get("rating", ""),  # MPAA rating
            "runtime": movie_data.get("runtime"),
            "budget": movie_data.get("budget"),
            "revenue": movie_data.get("revenue"),

            # Collection
            "collection": movie_data.get("collection"),

            # Cast (top 10)
            "cast": movie_data.get("cast", [])[:10],

            # Crew
            "crew": crew_formatted,

            # Keywords
            "keywords": movie_data.get("keywords", []),

            # Images
            "images": images,

            # Trailer
            "trailer_key": movie_data.get("trailer_key", ""),

            # Similar movies
            "similar_movies": movie_data.get("similar_movies", []),

            # Production companies
            "production_companies": movie_data.get("production_companies", []),
        }

    def _build_tv_payload(self, tv_data: dict, episode_data: dict = None) -> dict:
        """Build the complete payload to send to n8n for TV shows.

        Args:
            tv_data: TMDb TV show metadata.
            episode_data: Optional episode-specific data.

        Returns:
            dict: Formatted payload for n8n webhook.
        """
        images = tv_data.get("images", {})
        if not images:
            images = {
                "poster": tv_data.get("poster_url", ""),
                "backdrop": tv_data.get("backdrop_url", ""),
                "logo": "",
            }

        payload = {
            "media_type": "tv",
            "title": tv_data.get("title", "") or tv_data.get("show_name", ""),
            "year": str(tv_data.get("year", "")),
            "tmdb_id": str(tv_data.get("tmdb_id", "")),
            "imdb_id": tv_data.get("imdb_id", ""),
            "tvdb_id": tv_data.get("tvdb_id"),
            "description": tv_data.get("description", "") or tv_data.get("plot", ""),
            "tagline": tv_data.get("tagline", ""),
            "genres": ", ".join(tv_data.get("genres", [])),
            "rating": tv_data.get("rating", ""),  # Content rating
            "status": tv_data.get("status", ""),
            "number_of_seasons": tv_data.get("number_of_seasons"),
            "number_of_episodes": tv_data.get("number_of_episodes"),

            # Cast
            "cast": tv_data.get("cast", [])[:10],

            # Creators
            "creators": tv_data.get("creators", []),

            # Keywords
            "keywords": tv_data.get("keywords", []),

            # Images
            "images": images,

            # Trailer
            "trailer_key": tv_data.get("trailer_key", ""),

            # Similar shows
            "similar_shows": tv_data.get("similar_shows", []),

            # Networks
            "networks": tv_data.get("networks", []),
        }

        # Add episode data if provided
        if episode_data:
            payload["episode"] = {
                "season": episode_data.get("season"),
                "episode": episode_data.get("episode"),
                "title": episode_data.get("title", "") or episode_data.get("episode_title", ""),
                "plot": episode_data.get("plot", "") or episode_data.get("episode_plot", ""),
                "aired": episode_data.get("aired", "") or episode_data.get("episode_air_date", ""),
            }

        return payload

    def _send_with_retry(self, payload: dict) -> Optional[dict]:
        """Send payload to n8n webhook with retry logic.

        Args:
            payload: JSON payload to send.

        Returns:
            dict or None: Response data, or None on complete failure.
        """
        delay = self.retry_delay

        for attempt in range(self.retry_count + 1):
            try:
                response = self._send_request(payload)
                if response:
                    return response

            except requests.exceptions.ConnectionError as e:
                logger.warning(
                    "n8n connection failed (attempt %d/%d): %s",
                    attempt + 1, self.retry_count + 1, str(e)
                )
            except requests.exceptions.Timeout as e:
                logger.warning(
                    "n8n request timed out (attempt %d/%d): %s",
                    attempt + 1, self.retry_count + 1, str(e)
                )
            except requests.exceptions.RequestException as e:
                logger.warning(
                    "n8n request failed (attempt %d/%d): %s",
                    attempt + 1, self.retry_count + 1, str(e)
                )

            # Wait before retry (exponential backoff)
            if attempt < self.retry_count:
                logger.info("Retrying in %.1f seconds...", delay)
                time.sleep(delay)
                delay *= 2  # Exponential backoff

        logger.error("n8n enrichment failed after %d attempts", self.retry_count + 1)
        return None

    def _send_request(self, payload: dict) -> Optional[dict]:
        """Send a single request to n8n webhook.

        Args:
            payload: JSON payload to send.

        Returns:
            dict or None: Parsed response, or None on failure.
        """
        logger.debug("Sending to n8n: %s", payload.get("title", "unknown"))

        response = self.session.post(
            self.webhook_url,
            json=payload,
            timeout=self.timeout
        )

        if response.status_code == 200:
            try:
                data = response.json()
                if data.get("success", True):  # Assume success if not specified
                    logger.info(
                        "n8n enrichment successful for: %s",
                        payload.get("title", "unknown")
                    )
                    return self._merge_response(payload, data)
                else:
                    logger.warning(
                        "n8n returned failure for: %s - %s",
                        payload.get("title", "unknown"),
                        data.get("error", "Unknown error")
                    )
                    return None
            except json.JSONDecodeError:
                logger.warning("n8n returned invalid JSON")
                return None
        else:
            logger.warning(
                "n8n returned status %d for: %s",
                response.status_code,
                payload.get("title", "unknown")
            )
            return None

    def _merge_response(self, original: dict, response: dict) -> dict:
        """Merge n8n response with original data.

        The enriched data includes:
        - family_description: AI-rewritten family-friendly description
        - content_warnings: Dict with violence, language, scary_content, mature_themes
        - age_recommendation: e.g., "Ages 10+"
        - custom_tags: List of AI-generated tags
        - similar_titles: List of similar title names

        Args:
            original: Original payload sent to n8n.
            response: Response from n8n.

        Returns:
            dict: Merged data with all original and enriched fields.
        """
        result = original.copy()

        # Add AI-enriched fields
        result["family_description"] = response.get("family_description", "")
        result["content_warnings"] = response.get("content_warnings", {})
        result["age_recommendation"] = response.get("age_recommendation", "")
        result["custom_tags"] = response.get("custom_tags", [])
        result["similar_titles"] = response.get("similar_titles", [])

        # Mark as enriched
        result["enriched"] = True
        result["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

        return result

    def is_available(self) -> bool:
        """Check if n8n webhook is available.

        Returns:
            bool: True if n8n is reachable.
        """
        try:
            # Try a simple GET request to check if n8n is up
            # Most webhooks won't respond to GET, but we can check connectivity
            response = self.session.get(
                self.webhook_url.replace("/webhook/", "/healthz/").split("/webhook/")[0] + "/healthz",
                timeout=5
            )
            return response.status_code in (200, 404)  # 404 is OK, means n8n is running
        except Exception:
            return False


class MockEnricher:
    """Mock enricher for testing without n8n connection.

    Generates placeholder AI-enriched data.
    """

    def enrich_movie(self, movie_data: dict) -> dict:
        """Generate mock enriched data for a movie."""
        return self._mock_enrich(movie_data, "movie")

    def enrich_tv_show(self, tv_data: dict, episode_data: dict = None) -> dict:
        """Generate mock enriched data for a TV show."""
        return self._mock_enrich(tv_data, "tv")

    def _mock_enrich(self, data: dict, media_type: str) -> dict:
        """Generate mock enrichment."""
        title = data.get("title", "") or data.get("show_name", "")
        description = data.get("description", "") or data.get("plot", "")

        result = data.copy()
        result["family_description"] = description or f"A {media_type} titled {title}."
        result["content_warnings"] = {
            "violence": "Not analyzed (mock mode)",
            "language": "Not analyzed (mock mode)",
            "scary_content": "Not analyzed (mock mode)",
            "mature_themes": "Not analyzed (mock mode)",
        }
        result["age_recommendation"] = "Check rating"
        result["custom_tags"] = data.get("genres", [])[:4]
        result["similar_titles"] = []
        result["enriched"] = True
        result["enriched_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["mock_enriched"] = True

        return result

    def is_available(self) -> bool:
        """Mock is always available."""
        return True

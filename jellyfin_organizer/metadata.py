"""Enhanced NFO metadata file creation for Jellyfin/Kodi/Emby with AI enrichment support."""

import logging
import os
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class NFOWriter:
    """Creates Jellyfin-compatible NFO files with comprehensive metadata and AI enrichment."""

    def create_movie_nfo(self, enriched_data: dict, output_path: str) -> bool:
        """Create a complete movie NFO file with TMDb data and AI enrichment.

        Args:
            enriched_data: Combined TMDb and AI-enriched metadata.
            output_path: Path where the NFO file should be written.

        Returns:
            bool: True if file was written successfully.
        """
        try:
            content = self._build_movie_nfo(enriched_data)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Movie NFO written: %s", output_path)
            return True
        except Exception:
            logger.exception("Failed to write movie NFO: %s", output_path)
            return False

    def create_tvshow_nfo(self, enriched_data: dict, output_path: str) -> bool:
        """Create a complete TV show NFO file (tvshow.nfo).

        Args:
            enriched_data: Combined TMDb and AI-enriched metadata.
            output_path: Path where the NFO file should be written.

        Returns:
            bool: True if file was written successfully.
        """
        try:
            content = self._build_tvshow_nfo(enriched_data)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("TV show NFO written: %s", output_path)
            return True
        except Exception:
            logger.exception("Failed to write TV show NFO: %s", output_path)
            return False

    def create_episode_nfo(self, episode_data: dict, show_data: dict, output_path: str) -> bool:
        """Create an episode NFO file.

        Args:
            episode_data: Episode-specific metadata.
            show_data: Parent show metadata.
            output_path: Path where the NFO file should be written.

        Returns:
            bool: True if file was written successfully.
        """
        try:
            content = self._build_episode_nfo(episode_data, show_data)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("Episode NFO written: %s", output_path)
            return True
        except Exception:
            logger.exception("Failed to write episode NFO: %s", output_path)
            return False

    def _build_movie_nfo(self, data: dict) -> str:
        """Build complete movie NFO XML content.

        Args:
            data: Combined TMDb and AI-enriched metadata.

        Returns:
            str: Formatted XML string.
        """
        root = ET.Element("movie")

        # Basic info
        self._add_element(root, "title", data.get("title", ""))

        original_title = data.get("original_title", "")
        if original_title and original_title != data.get("title"):
            self._add_element(root, "originaltitle", original_title)

        if data.get("year"):
            self._add_element(root, "year", str(data["year"]))

        # Use AI family_description if available, otherwise use original description
        plot = data.get("family_description") or data.get("description") or data.get("plot", "")
        if plot:
            self._add_element(root, "plot", plot)
            # Outline is first 200 chars
            outline = plot[:200] + "..." if len(plot) > 200 else plot
            self._add_element(root, "outline", outline)

        if data.get("tagline"):
            self._add_element(root, "tagline", data["tagline"])

        if data.get("runtime"):
            self._add_element(root, "runtime", str(data["runtime"]))

        # MPAA rating
        if data.get("rating"):
            self._add_element(root, "mpaa", data["rating"])

        # Unique IDs
        if data.get("tmdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
            uid.text = str(data["tmdb_id"])
            self._add_element(root, "tmdbid", str(data["tmdb_id"]))

        if data.get("imdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "imdb"})
            uid.text = data["imdb_id"]

        # Ratings block (TMDb rating)
        if data.get("tmdb_rating") is not None:
            ratings_el = ET.SubElement(root, "ratings")
            rating_el = ET.SubElement(ratings_el, "rating", {
                "name": "tmdb",
                "max": "10",
                "default": "true",
            })
            self._add_element(rating_el, "value", str(data["tmdb_rating"]))
            if data.get("tmdb_votes") is not None:
                self._add_element(rating_el, "votes", str(data["tmdb_votes"]))

        # Genres
        for genre in data.get("genres", []):
            self._add_element(root, "genre", genre)

        # AI Custom Tags
        for tag in data.get("custom_tags", []):
            self._add_element(root, "tag", tag)

        # TMDb Keywords (for advanced filtering)
        for keyword in data.get("keywords", []):
            self._add_element(root, "tag", keyword)

        # Collection Info
        collection = data.get("collection")
        if collection:
            set_el = ET.SubElement(root, "set")
            self._add_element(set_el, "name", collection.get("name", ""))
            if collection.get("id"):
                self._add_element(set_el, "tmdbid", str(collection["id"]))

        # Cast (top actors)
        for actor in data.get("cast", [])[:10]:
            actor_el = ET.SubElement(root, "actor")
            self._add_element(actor_el, "name", actor.get("name", ""))
            role = actor.get("character") or actor.get("role", "")
            self._add_element(actor_el, "role", role)
            self._add_element(actor_el, "order", str(actor.get("order", 0)))
            if actor.get("thumb"):
                self._add_element(actor_el, "thumb", actor["thumb"])

        # Crew (directors, writers)
        crew = data.get("crew", {})
        if isinstance(crew, dict):
            for director in crew.get("directors", []):
                self._add_element(root, "director", director)
            for writer in crew.get("writers", []):
                self._add_element(root, "credits", writer)
        else:
            # Handle flat director/writer lists
            for director in data.get("directors", []):
                self._add_element(root, "director", director)
            for writer in data.get("writers", []):
                self._add_element(root, "credits", writer)

        # AI Content Warnings (as tags for Jellyfin filtering)
        content_warnings = data.get("content_warnings", {})
        if content_warnings:
            if content_warnings.get("violence"):
                self._add_element(root, "tag", f"Violence: {content_warnings['violence'].split(':')[0] if ':' in content_warnings['violence'] else content_warnings['violence']}")
            if content_warnings.get("language"):
                self._add_element(root, "tag", f"Language: {content_warnings['language'].split(':')[0] if ':' in content_warnings['language'] else content_warnings['language']}")
            if content_warnings.get("scary_content"):
                self._add_element(root, "tag", f"Scary: {content_warnings['scary_content'].split(':')[0] if ':' in content_warnings['scary_content'] else content_warnings['scary_content']}")

        # Age recommendation
        if data.get("age_recommendation"):
            self._add_element(root, "tag", f"Age: {data['age_recommendation']}")

        # Images
        images = data.get("images", {})
        poster_url = images.get("poster") or data.get("poster_url", "")
        backdrop_url = images.get("backdrop") or data.get("backdrop_url", "")
        logo_url = images.get("logo", "")

        if poster_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            thumb.text = poster_url

        if backdrop_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "banner"})
            thumb.text = backdrop_url
            fanart = ET.SubElement(root, "fanart")
            fanart_thumb = ET.SubElement(fanart, "thumb")
            fanart_thumb.text = backdrop_url

        if logo_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "clearlogo"})
            thumb.text = logo_url

        # Trailer (YouTube format for Kodi/Jellyfin)
        if data.get("trailer_key"):
            # Format: plugin://plugin.video.youtube/?action=play_video&videoid=KEY
            trailer_url = f"plugin://plugin.video.youtube/?action=play_video&videoid={data['trailer_key']}"
            self._add_element(root, "trailer", trailer_url)

        # Production companies / Studios
        for studio in data.get("production_companies", data.get("studios", []))[:5]:
            self._add_element(root, "studio", studio)

        # AI Similar Titles
        for similar in data.get("similar_titles", []):
            self._add_element(root, "similar", similar)

        # Timestamps
        self._add_element(root, "dateadded", time.strftime("%Y-%m-%dT%H:%M:%S"))
        if data.get("enriched_at"):
            self._add_element(root, "enriched_at", data["enriched_at"])

        # Premiered date
        if data.get("premiered"):
            self._add_element(root, "premiered", data["premiered"])

        return self._prettify_xml(root)

    def _build_tvshow_nfo(self, data: dict) -> str:
        """Build complete TV show NFO XML content.

        Args:
            data: Combined TMDb and AI-enriched metadata.

        Returns:
            str: Formatted XML string.
        """
        root = ET.Element("tvshow")

        # Basic info
        title = data.get("title", "") or data.get("show_name", "")
        self._add_element(root, "title", title)

        original_title = data.get("original_title", "")
        if original_title and original_title != title:
            self._add_element(root, "originaltitle", original_title)

        if data.get("year"):
            self._add_element(root, "year", str(data["year"]))

        # Use AI family_description if available
        plot = data.get("family_description") or data.get("description") or data.get("plot", "")
        if plot:
            self._add_element(root, "plot", plot)

        if data.get("tagline"):
            self._add_element(root, "tagline", data["tagline"])

        if data.get("status"):
            self._add_element(root, "status", data["status"])

        # Content rating
        if data.get("rating"):
            self._add_element(root, "mpaa", data["rating"])

        # Unique IDs
        if data.get("tmdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
            uid.text = str(data["tmdb_id"])

        if data.get("imdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "imdb"})
            uid.text = data["imdb_id"]

        if data.get("tvdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "tvdb"})
            uid.text = str(data["tvdb_id"])

        # Ratings
        if data.get("tmdb_rating") is not None:
            ratings_el = ET.SubElement(root, "ratings")
            rating_el = ET.SubElement(ratings_el, "rating", {
                "name": "tmdb",
                "max": "10",
                "default": "true",
            })
            self._add_element(rating_el, "value", str(data["tmdb_rating"]))
            if data.get("tmdb_votes") is not None:
                self._add_element(rating_el, "votes", str(data["tmdb_votes"]))

        # Genres
        for genre in data.get("genres", []):
            self._add_element(root, "genre", genre)

        # AI Custom Tags
        for tag in data.get("custom_tags", []):
            self._add_element(root, "tag", tag)

        # Keywords
        for keyword in data.get("keywords", []):
            self._add_element(root, "tag", keyword)

        # Cast
        for actor in data.get("cast", [])[:10]:
            actor_el = ET.SubElement(root, "actor")
            self._add_element(actor_el, "name", actor.get("name", ""))
            role = actor.get("character") or actor.get("role", "")
            self._add_element(actor_el, "role", role)
            self._add_element(actor_el, "order", str(actor.get("order", 0)))
            if actor.get("thumb"):
                self._add_element(actor_el, "thumb", actor["thumb"])

        # Networks/Studios
        for network in data.get("networks", data.get("studios", [])):
            self._add_element(root, "studio", network)

        # Season/episode counts
        if data.get("number_of_seasons"):
            self._add_element(root, "season", str(data["number_of_seasons"]))
        if data.get("number_of_episodes"):
            self._add_element(root, "episode", str(data["number_of_episodes"]))

        # Images
        images = data.get("images", {})
        poster_url = images.get("poster") or data.get("poster_url", "")
        backdrop_url = images.get("backdrop") or data.get("backdrop_url", "")

        if poster_url:
            thumb = ET.SubElement(root, "thumb", {"aspect": "poster"})
            thumb.text = poster_url

        if backdrop_url:
            fanart = ET.SubElement(root, "fanart")
            fanart_thumb = ET.SubElement(fanart, "thumb")
            fanart_thumb.text = backdrop_url

        # Trailer
        if data.get("trailer_key"):
            trailer_url = f"plugin://plugin.video.youtube/?action=play_video&videoid={data['trailer_key']}"
            self._add_element(root, "trailer", trailer_url)

        # Content warnings
        content_warnings = data.get("content_warnings", {})
        if content_warnings:
            if content_warnings.get("violence"):
                self._add_element(root, "tag", f"Violence: {content_warnings['violence'].split(':')[0] if ':' in content_warnings['violence'] else content_warnings['violence']}")

        # Age recommendation
        if data.get("age_recommendation"):
            self._add_element(root, "tag", f"Age: {data['age_recommendation']}")

        # Timestamps
        self._add_element(root, "dateadded", time.strftime("%Y-%m-%dT%H:%M:%S"))
        if data.get("premiered"):
            self._add_element(root, "premiered", data["premiered"])

        return self._prettify_xml(root)

    def _build_episode_nfo(self, episode_data: dict, show_data: dict = None) -> str:
        """Build episode NFO XML content.

        Args:
            episode_data: Episode-specific metadata.
            show_data: Optional parent show metadata.

        Returns:
            str: Formatted XML string.
        """
        root = ET.Element("episodedetails")

        # Episode title
        title = episode_data.get("title", "") or episode_data.get("episode_title", "")
        self._add_element(root, "title", title)

        # Show title
        if show_data:
            show_title = show_data.get("title", "") or show_data.get("show_name", "")
            self._add_element(root, "showtitle", show_title)

        # Season and episode numbers
        if episode_data.get("season") is not None:
            self._add_element(root, "season", str(episode_data["season"]))
        if episode_data.get("episode") is not None:
            self._add_element(root, "episode", str(episode_data["episode"]))

        # Air date
        aired = episode_data.get("aired", "") or episode_data.get("episode_air_date", "")
        if aired:
            self._add_element(root, "aired", aired)

        # Runtime
        if episode_data.get("runtime"):
            self._add_element(root, "runtime", str(episode_data["runtime"]))

        # Plot
        plot = episode_data.get("plot", "") or episode_data.get("episode_plot", "")
        if plot:
            self._add_element(root, "plot", plot)

        # Ratings
        if episode_data.get("rating") is not None:
            ratings_el = ET.SubElement(root, "ratings")
            rating_el = ET.SubElement(ratings_el, "rating", {
                "name": "tmdb",
                "max": "10",
                "default": "true",
            })
            self._add_element(rating_el, "value", str(episode_data["rating"]))
            if episode_data.get("votes") is not None:
                self._add_element(rating_el, "votes", str(episode_data["votes"]))

        # Unique ID
        if episode_data.get("tmdb_id"):
            uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
            uid.text = str(episode_data["tmdb_id"])

        # Directors
        for director in episode_data.get("directors", []):
            self._add_element(root, "director", director)

        # Writers
        for writer in episode_data.get("writers", []):
            self._add_element(root, "credits", writer)

        # Guest stars
        for star in episode_data.get("guest_stars", []):
            actor_el = ET.SubElement(root, "actor")
            self._add_element(actor_el, "name", star.get("name", ""))
            self._add_element(actor_el, "role", star.get("role", ""))
            if star.get("thumb"):
                self._add_element(actor_el, "thumb", star["thumb"])

        # Still image
        if episode_data.get("still_url"):
            thumb = ET.SubElement(root, "thumb")
            thumb.text = episode_data["still_url"]

        return self._prettify_xml(root)

    def _add_element(self, parent: ET.Element, tag: str, text: str) -> ET.Element:
        """Add a text element to an XML parent."""
        el = ET.SubElement(parent, tag)
        el.text = str(text) if text else ""
        return el

    def _prettify_xml(self, element: ET.Element) -> str:
        """Convert an XML element to a formatted string with proper indentation.

        Args:
            element: XML Element to format.

        Returns:
            str: Formatted XML string with declaration.
        """
        lines = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>']
        self._indent_element(element, lines, level=0)
        return "\n".join(lines) + "\n"

    def _indent_element(self, element: ET.Element, lines: List[str], level: int):
        """Recursively build indented XML lines."""
        indent = "  " * level
        tag = element.tag
        attribs = "".join(f' {k}="{self._escape_xml(v)}"' for k, v in element.attrib.items())

        children = list(element)
        if children:
            lines.append(f"{indent}<{tag}{attribs}>")
            for child in children:
                self._indent_element(child, lines, level + 1)
            lines.append(f"{indent}</{tag}>")
        elif element.text:
            text = self._escape_xml(element.text)
            lines.append(f"{indent}<{tag}{attribs}>{text}</{tag}>")
        else:
            lines.append(f"{indent}<{tag}{attribs} />")

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        if not text:
            return ""
        text = str(text)
        text = text.replace("&", "&amp;")
        text = text.replace("<", "&lt;")
        text = text.replace(">", "&gt;")
        text = text.replace('"', "&quot;")
        return text


# Legacy functions for compatibility
def create_nfo_content(movie_data: dict) -> str:
    """Create NFO XML content from movie metadata (legacy function)."""
    writer = NFOWriter()
    return writer._build_movie_nfo(movie_data)


def write_nfo_file(filepath: str, movie_data: dict) -> bool:
    """Write an NFO file for a movie (legacy function)."""
    writer = NFOWriter()
    return writer.create_movie_nfo(movie_data, filepath)


def create_tvshow_nfo_content(show_data: dict) -> str:
    """Create NFO XML content for a TV show (legacy function)."""
    writer = NFOWriter()
    return writer._build_tvshow_nfo(show_data)


def write_tvshow_nfo(show_folder: str, show_data: dict) -> bool:
    """Write a tvshow.nfo file for a TV show (legacy function)."""
    writer = NFOWriter()
    nfo_path = os.path.join(show_folder, "tvshow.nfo")
    return writer.create_tvshow_nfo(show_data, nfo_path)


def create_episode_nfo_content(episode_data: dict, show_data: dict = None) -> str:
    """Create NFO XML content for a TV episode (legacy function)."""
    writer = NFOWriter()
    return writer._build_episode_nfo(episode_data, show_data)


def write_episode_nfo(episode_path: str, episode_data: dict, show_data: dict = None) -> bool:
    """Write an episode NFO file (legacy function)."""
    writer = NFOWriter()
    nfo_path = os.path.splitext(episode_path)[0] + ".nfo"
    return writer.create_episode_nfo(episode_data, show_data, nfo_path)

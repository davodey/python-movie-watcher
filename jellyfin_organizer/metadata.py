"""NFO metadata file creation for Jellyfin/Kodi/Emby."""

import logging
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)


def create_nfo_content(movie_data):
    """Create NFO XML content from movie metadata.

    Args:
        movie_data: dict with movie metadata from TMDb.

    Returns:
        str: XML string for the NFO file.
    """
    root = ET.Element("movie")

    _add_text_element(root, "title", movie_data.get("title", ""))

    original_title = movie_data.get("original_title", "")
    if original_title and original_title != movie_data.get("title"):
        _add_text_element(root, "originaltitle", original_title)

    if movie_data.get("year"):
        _add_text_element(root, "year", str(movie_data["year"]))

    if movie_data.get("premiered"):
        _add_text_element(root, "premiered", movie_data["premiered"])

    if movie_data.get("runtime"):
        _add_text_element(root, "runtime", str(movie_data["runtime"]))

    # Ratings block
    if movie_data.get("rating") is not None:
        ratings_el = ET.SubElement(root, "ratings")
        rating_el = ET.SubElement(ratings_el, "rating", {
            "name": "tmdb",
            "max": "10",
            "default": "true",
        })
        _add_text_element(rating_el, "value", str(movie_data["rating"]))
        if movie_data.get("votes") is not None:
            _add_text_element(rating_el, "votes", str(movie_data["votes"]))

    if movie_data.get("plot"):
        _add_text_element(root, "plot", movie_data["plot"])

    if movie_data.get("tagline"):
        _add_text_element(root, "tagline", movie_data["tagline"])

    # Unique IDs
    if movie_data.get("tmdb_id"):
        uid = ET.SubElement(root, "uniqueid", {"type": "tmdb", "default": "true"})
        uid.text = str(movie_data["tmdb_id"])

    if movie_data.get("imdb_id"):
        uid = ET.SubElement(root, "uniqueid", {"type": "imdb"})
        uid.text = movie_data["imdb_id"]

    # Genres
    for genre in movie_data.get("genres", []):
        _add_text_element(root, "genre", genre)

    # Studios
    for studio in movie_data.get("studios", []):
        _add_text_element(root, "studio", studio)

    # Countries
    for country in movie_data.get("countries", []):
        _add_text_element(root, "country", country)

    # Cast
    for actor in movie_data.get("cast", []):
        actor_el = ET.SubElement(root, "actor")
        _add_text_element(actor_el, "name", actor.get("name", ""))
        _add_text_element(actor_el, "role", actor.get("role", ""))
        _add_text_element(actor_el, "order", str(actor.get("order", 0)))
        if actor.get("thumb"):
            _add_text_element(actor_el, "thumb", actor["thumb"])

    # Directors
    for director in movie_data.get("directors", []):
        _add_text_element(root, "director", director)

    # Writers
    for writer in movie_data.get("writers", []):
        _add_text_element(root, "credits", writer)

    # Trailer
    if movie_data.get("trailer"):
        _add_text_element(root, "trailer", movie_data["trailer"])

    return _prettify_xml(root)


def write_nfo_file(filepath, movie_data):
    """Write an NFO file for a movie.

    Args:
        filepath: Path where the .nfo file should be written.
        movie_data: dict with movie metadata.

    Returns:
        bool: True if file was written successfully.
    """
    try:
        content = create_nfo_content(movie_data)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("NFO file written: %s", filepath)
        return True
    except Exception:
        logger.exception("Failed to write NFO file: %s", filepath)
        return False


def _add_text_element(parent, tag, text):
    """Add a text element to an XML parent."""
    el = ET.SubElement(parent, tag)
    el.text = text
    return el


def _prettify_xml(element):
    """Convert an XML element to a formatted string with proper indentation.

    Args:
        element: XML Element to format.

    Returns:
        str: Formatted XML string with declaration.
    """
    lines = ['<?xml version="1.0" encoding="utf-8"?>']
    _indent_element(element, lines, level=0)
    return "\n".join(lines) + "\n"


def _indent_element(element, lines, level):
    """Recursively build indented XML lines."""
    indent = "  " * level
    tag = element.tag
    attribs = "".join(f' {k}="{v}"' for k, v in element.attrib.items())

    children = list(element)
    if children:
        lines.append(f"{indent}<{tag}{attribs}>")
        for child in children:
            _indent_element(child, lines, level + 1)
        lines.append(f"{indent}</{tag}>")
    elif element.text:
        # Escape XML special characters in text
        text = _escape_xml(element.text)
        lines.append(f"{indent}<{tag}{attribs}>{text}</{tag}>")
    else:
        lines.append(f"{indent}<{tag}{attribs} />")


def _escape_xml(text):
    """Escape XML special characters."""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text

"""Artwork downloading for movie posters and backdrops."""

import logging

import requests

logger = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT = 60  # seconds


def download_image(url, destination_path):
    """Download an image from a URL to a local file.

    Args:
        url: Image URL to download.
        destination_path: Local file path to save the image.

    Returns:
        bool: True if download succeeded.
    """
    if not url:
        logger.warning("No URL provided for image download")
        return False

    try:
        response = requests.get(url, timeout=DOWNLOAD_TIMEOUT, stream=True)
        response.raise_for_status()

        # Verify we got image content
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("image/"):
            logger.warning("Non-image content type received: %s", content_type)
            return False

        with open(destination_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info("Downloaded image: %s", destination_path)
        return True

    except requests.RequestException:
        logger.exception("Failed to download image from %s", url)
        return False


def download_movie_artwork(movie_data, destination_dir):
    """Download poster and backdrop images for a movie.

    Args:
        movie_data: dict with 'poster_url' and 'backdrop_url' keys.
        destination_dir: Directory to save images in.

    Returns:
        dict: {'poster': bool, 'backdrop': bool} indicating success of each.
    """
    import os

    results = {"poster": False, "backdrop": False}

    poster_url = movie_data.get("poster_url", "")
    if poster_url:
        poster_path = os.path.join(destination_dir, "poster.jpg")
        results["poster"] = download_image(poster_url, poster_path)

    backdrop_url = movie_data.get("backdrop_url", "")
    if backdrop_url:
        backdrop_path = os.path.join(destination_dir, "backdrop.jpg")
        results["backdrop"] = download_image(backdrop_url, backdrop_path)

    return results

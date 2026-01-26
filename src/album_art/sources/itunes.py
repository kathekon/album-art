"""iTunes Search API for high-resolution album artwork."""

import logging

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)

# Simple in-memory cache for iTunes lookups
_artwork_cache: dict[str, str | None] = {}

# Reusable client for connection pooling
_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    """Get or create the HTTP client."""
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=15.0),
            follow_redirects=True,
        )
    return _http_client


async def get_itunes_artwork(artist: str, album: str) -> str | None:
    """Look up high-res album art from iTunes Search API.

    Args:
        artist: Artist name
        album: Album name

    Returns:
        URL to high-resolution artwork, or None if not found
    """
    settings = get_settings()
    if not settings.artwork.prefer_itunes:
        return None

    # Build cache key
    cache_key = f"{artist}|{album}".lower().strip()
    if cache_key in _artwork_cache:
        return _artwork_cache[cache_key]

    # Build search query
    query = f"{artist} {album}".strip()
    if not query:
        return None

    try:
        client = _get_client()
        resp = await client.get(
            "https://itunes.apple.com/search",
            params={
                "term": query,
                "entity": "album",
                "limit": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("resultCount", 0) > 0:
            art_url = data["results"][0].get("artworkUrl100", "")
            if art_url:
                # Replace 100x100 with configured size for higher resolution
                # iTunes supports sizes up to 3000x3000
                size = settings.artwork.itunes_size
                high_res_url = art_url.replace("100x100bb", f"{size}x{size}bb")
                logger.info(f"iTunes artwork found for '{query}': {size}x{size}")
                _artwork_cache[cache_key] = high_res_url
                return high_res_url

        logger.debug(f"No iTunes artwork found for '{query}'")
        _artwork_cache[cache_key] = None
        return None

    except httpx.TimeoutException:
        logger.warning(f"iTunes lookup timed out for '{query}'")
        return None
    except Exception as e:
        logger.warning(f"iTunes lookup failed for '{query}': {e}")
        return None

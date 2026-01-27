"""iTunes Search API for high-resolution album artwork."""

import logging
import re
import time

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


def _clean_album_name(album: str) -> str:
    """Strip edition markers that confuse iTunes search.

    Albums from Sonos often include suffixes like "(Expanded Edition)",
    "(Deluxe)", "(Remastered)", etc. These can cause iTunes to return
    wrong results (e.g., "Charlie Brown Christmas (Expanded Edition)"
    instead of "Filter - Title Of Record (Expanded Edition)").
    """
    # Remove common edition/version markers in parentheses or brackets
    patterns = [
        r"\s*\([^)]*(?:edition|deluxe|remaster|bonus|anniversary|version)[^)]*\)",
        r"\s*\[[^\]]*(?:edition|deluxe|remaster|bonus|anniversary|version)[^\]]*\]",
    ]
    cleaned = album
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

# Simple in-memory cache for iTunes lookups
_artwork_cache: dict[str, str | None] = {}

# Reusable client for connection pooling
_http_client: httpx.AsyncClient | None = None

# Rate limit backoff - unix timestamp when we can retry
_rate_limit_until: float = 0


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
    global _rate_limit_until

    settings = get_settings()
    if not settings.artwork.prefer_itunes:
        return None

    # Build cache key - check cache first (even during rate limit)
    cache_key = f"{artist}|{album}".lower().strip()
    if cache_key in _artwork_cache:
        return _artwork_cache[cache_key]

    # Check if we're in rate limit backoff (only applies to new lookups)
    if time.time() < _rate_limit_until:
        logger.debug("iTunes rate limited, skipping lookup")
        return None

    # Build search query - clean album name to avoid wrong matches
    clean_album = _clean_album_name(album)
    query = f"{artist} {clean_album}".strip()
    if not query:
        return None

    try:
        client = _get_client()
        resp = await client.get(
            "https://itunes.apple.com/search",
            params={
                "term": query,
                "entity": "album",
                "limit": 5,  # Get multiple results to find best match
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Find best matching result - verify artist matches
        artist_lower = artist.lower()
        for result in data.get("results", []):
            result_artist = result.get("artistName", "").lower()
            # Skip results with empty artist - would incorrectly match anything
            # (because "" in "any string" returns True in Python)
            if not result_artist:
                continue
            # Check if artist name matches (allow partial match for "The Band" vs "Band")
            if artist_lower in result_artist or result_artist in artist_lower:
                art_url = result.get("artworkUrl100", "")
                if art_url:
                    # Replace 100x100 with configured size for higher resolution
                    # iTunes supports sizes up to 3000x3000
                    size = settings.artwork.itunes_size
                    high_res_url = art_url.replace("100x100bb", f"{size}x{size}bb")
                    logger.info(f"iTunes artwork found for '{query}' (artist: {result_artist}): {size}x{size}")
                    _artwork_cache[cache_key] = high_res_url
                    return high_res_url

        logger.debug(f"No iTunes artwork found for '{query}' (no artist match)")
        _artwork_cache[cache_key] = None
        return None

    except httpx.TimeoutException:
        logger.warning(f"iTunes lookup timed out for '{query}'")
        return None
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            # Rate limited - back off for 60 seconds
            _rate_limit_until = time.time() + 60
            logger.warning("iTunes rate limited (429), backing off for 60s")
        else:
            logger.warning(f"iTunes HTTP error for '{query}': {e.response.status_code}")
        return None
    except Exception as e:
        logger.warning(f"iTunes lookup failed for '{query}': {e}")
        return None

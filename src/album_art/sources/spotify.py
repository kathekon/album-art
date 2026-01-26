"""Spotify integration using Spotipy library."""

import asyncio
import logging
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from ..config import get_settings
from .base import MusicSource, TrackInfo

logger = logging.getLogger(__name__)


class SpotifySource(MusicSource):
    """Spotify music source using Spotipy library."""

    SCOPE = "user-read-currently-playing user-read-playback-state"

    def __init__(self):
        self._client: spotipy.Spotify | None = None
        self._auth_manager: SpotifyOAuth | None = None

    @property
    def name(self) -> str:
        return "spotify"

    @property
    def is_available(self) -> bool:
        settings = get_settings()
        if not settings.spotify.enabled:
            return False
        if not settings.spotify.client_id or not settings.spotify.client_secret:
            logger.debug("Spotify credentials not configured")
            return False
        # Check if we have cached credentials
        if not Path(settings.spotify.cache_path).exists():
            logger.debug("Spotify token cache not found - run spotify-auth.py first")
            return False
        return True

    def _get_client(self) -> spotipy.Spotify | None:
        """Get or create Spotify client."""
        if self._client is not None:
            return self._client

        settings = get_settings()
        if not settings.spotify.client_id or not settings.spotify.client_secret:
            return None

        try:
            self._auth_manager = SpotifyOAuth(
                client_id=settings.spotify.client_id,
                client_secret=settings.spotify.client_secret,
                redirect_uri=settings.spotify.redirect_uri,
                scope=self.SCOPE,
                cache_path=settings.spotify.cache_path,
                open_browser=False,
            )

            # This will use cached token or fail if no cache exists
            token_info = self._auth_manager.get_cached_token()
            if not token_info:
                logger.warning("No Spotify token cache found")
                return None

            self._client = spotipy.Spotify(auth_manager=self._auth_manager)
            logger.info("Spotify client initialized")
            return self._client
        except Exception as e:
            logger.error(f"Failed to initialize Spotify client: {e}")
            return None

    async def get_current_track(self) -> TrackInfo | None:
        """Get currently playing track from Spotify."""
        client = self._get_client()
        if client is None:
            return None

        # Run blocking Spotipy calls in thread pool
        loop = asyncio.get_event_loop()
        try:
            playback = await loop.run_in_executor(None, client.current_playback)
        except Exception as e:
            logger.error(f"Error getting Spotify playback: {e}")
            # Token might be expired, clear client to retry
            self._client = None
            return None

        if not playback or not playback.get("item"):
            return None

        item = playback["item"]

        # Handle both tracks and episodes (podcasts)
        if item.get("type") == "episode":
            # Podcast episode
            title = item.get("name", "Unknown Episode")
            artist = item.get("show", {}).get("name", "Unknown Show")
            album = "Podcast"
            images = item.get("images", [])
        else:
            # Music track
            title = item.get("name", "Unknown Track")
            artists = item.get("artists", [])
            artist = ", ".join(a.get("name", "") for a in artists) or "Unknown Artist"
            album = item.get("album", {}).get("name", "Unknown Album")
            images = item.get("album", {}).get("images", [])

        # Get highest resolution image (first in list is largest)
        album_art_url = None
        if images:
            # Prefer 640x640, fall back to largest available
            for img in images:
                if img.get("width", 0) >= 640:
                    album_art_url = img.get("url")
                    break
            if not album_art_url and images:
                album_art_url = images[0].get("url")

        return TrackInfo(
            source=self.name,
            title=title,
            artist=artist,
            album=album,
            album_art_url=album_art_url,
            is_playing=playback.get("is_playing", False),
            position_ms=playback.get("progress_ms"),
            duration_ms=item.get("duration_ms"),
        )

"""Background polling service for music sources."""

import asyncio
import logging

from ..config import get_settings
from ..sources.base import MusicSource, TrackInfo
from ..sources.sonos import SonosSource
from ..sources.spotify import SpotifySource
from .state import playback_state

logger = logging.getLogger(__name__)


class Poller:
    """Background service that polls music sources."""

    def __init__(self):
        self._sources: list[MusicSource] = []
        self._running = False
        self._task: asyncio.Task | None = None

        # Initialize sources
        settings = get_settings()
        if settings.sonos.enabled:
            self._sources.append(SonosSource())
        if settings.spotify.enabled:
            self._sources.append(SpotifySource())

    @property
    def sources(self) -> list[MusicSource]:
        return self._sources

    async def start(self):
        """Start the background polling task."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        available = [s.name for s in self._sources if s.is_available]
        logger.info(f"Poller started with available sources: {available}")

    async def stop(self):
        """Stop the background polling task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Poller stopped")

    async def _poll_loop(self):
        """Main polling loop."""
        settings = get_settings()
        while self._running:
            try:
                track = await self._poll_sources()
                await playback_state.update(track)
            except Exception as e:
                logger.error(f"Polling error: {e}")

            await asyncio.sleep(settings.polling.interval)

    async def _poll_sources(self) -> TrackInfo | None:
        """Poll all sources and return the best current track."""
        # Poll all sources concurrently
        tasks = [source.get_current_track() for source in self._sources if source.is_available]

        if not tasks:
            return None

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and None results
        tracks = [r for r in results if isinstance(r, TrackInfo)]

        if not tracks:
            return None

        # Prioritize: playing track > any track, Spotify > Sonos (typically higher quality art)
        playing_tracks = [t for t in tracks if t.is_playing]
        if playing_tracks:
            # Prefer Spotify for higher quality art
            for t in playing_tracks:
                if t.source == "spotify":
                    return t
            return playing_tracks[0]

        # Nothing playing, return most recent paused track
        return max(tracks, key=lambda t: t.timestamp)


# Global singleton
poller = Poller()

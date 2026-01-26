"""Sonos integration using SoCo library."""

import asyncio
import logging

import soco
from soco import SoCo

from ..config import get_settings
from .base import MusicSource, TrackInfo

logger = logging.getLogger(__name__)


class SonosSource(MusicSource):
    """Sonos music source using SoCo library."""

    def __init__(self):
        self._device: SoCo | None = None
        self._discovery_attempted = False

    @property
    def name(self) -> str:
        return "sonos"

    @property
    def is_available(self) -> bool:
        settings = get_settings()
        if not settings.sonos.enabled:
            return False
        return self._get_device() is not None

    def _get_device(self) -> SoCo | None:
        """Get or discover Sonos device."""
        if self._device is not None:
            return self._device

        if self._discovery_attempted:
            return None

        self._discovery_attempted = True
        settings = get_settings()

        # Try specific IP first
        if settings.sonos.ip:
            try:
                self._device = SoCo(settings.sonos.ip)
                # Verify it's reachable
                _ = self._device.player_name
                logger.info(f"Connected to Sonos at {settings.sonos.ip}")
                return self._device
            except Exception as e:
                logger.warning(f"Could not connect to Sonos at {settings.sonos.ip}: {e}")

        # Auto-discover
        try:
            logger.info("Discovering Sonos devices...")
            devices = list(soco.discover(timeout=5) or [])
            if not devices:
                logger.warning("No Sonos devices found")
                return None

            # Filter by room name if specified
            if settings.sonos.room:
                for device in devices:
                    if device.player_name.lower() == settings.sonos.room.lower():
                        self._device = device
                        logger.info(f"Connected to Sonos: {device.player_name}")
                        return self._device
                logger.warning(f"Room '{settings.sonos.room}' not found")

            # Use first device found
            self._device = devices[0]
            logger.info(f"Connected to Sonos: {self._device.player_name}")
            return self._device
        except Exception as e:
            logger.error(f"Sonos discovery failed: {e}")
            return None

    async def get_current_track(self) -> TrackInfo | None:
        """Get currently playing track from Sonos."""
        device = self._get_device()
        if device is None:
            return None

        # Run blocking SoCo calls in thread pool
        loop = asyncio.get_event_loop()
        try:
            track_info = await loop.run_in_executor(None, device.get_current_track_info)
            transport_info = await loop.run_in_executor(None, device.get_current_transport_info)
        except Exception as e:
            logger.error(f"Error getting Sonos track info: {e}")
            # Reset device to retry discovery next time
            self._device = None
            self._discovery_attempted = False
            return None

        # Check if actually playing
        playback_state = transport_info.get("current_transport_state", "")
        is_playing = playback_state == "PLAYING"

        title = track_info.get("title", "")
        if not title:
            return None

        # Construct full album art URL
        album_art = track_info.get("album_art", "")
        if album_art and not album_art.startswith("http"):
            album_art = f"http://{device.ip_address}:1400{album_art}"

        return TrackInfo(
            source=self.name,
            title=title,
            artist=track_info.get("artist", "") or "Unknown Artist",
            album=track_info.get("album", "") or "Unknown Album",
            album_art_url=album_art or None,
            is_playing=is_playing,
            position_ms=self._parse_time(track_info.get("position", "")),
            duration_ms=self._parse_time(track_info.get("duration", "")),
        )

    @staticmethod
    def _parse_time(time_str: str) -> int | None:
        """Parse time string (H:MM:SS or M:SS) to milliseconds."""
        if not time_str:
            return None
        parts = time_str.split(":")
        try:
            if len(parts) == 3:
                return (int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])) * 1000
            elif len(parts) == 2:
                return (int(parts[0]) * 60 + int(parts[1])) * 1000
        except ValueError:
            return None
        return None

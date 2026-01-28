"""Sonos integration using SoCo library."""

import asyncio
import logging

import soco
from soco import SoCo

from ..config import get_settings
from .base import MusicSource, TrackInfo
from .itunes import get_itunes_artwork

logger = logging.getLogger(__name__)


class SonosSource(MusicSource):
    """Sonos music source using SoCo library."""

    def __init__(self):
        self._device: SoCo | None = None
        self._room_name: str | None = None
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
                device = SoCo(settings.sonos.ip)
                # Verify it's actually a Sonos device by checking required attributes
                # This will fail if the IP points to a non-Sonos device
                player_name = device.player_name
                # Additional validation: check for Sonos-specific attributes
                _ = device.uid  # Unique ID - only Sonos devices have this
                self._device = device
                self._room_name = player_name
                logger.info(f"Connected to Sonos '{player_name}' at {settings.sonos.ip}")
                return self._device
            except Exception as e:
                logger.warning(
                    f"Device at {settings.sonos.ip} is not a valid Sonos speaker: {e}"
                )

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
                        self._room_name = device.player_name
                        logger.info(f"Connected to Sonos: {device.player_name}")
                        return self._device
                logger.warning(f"Room '{settings.sonos.room}' not found")

            # Use first device found
            self._device = devices[0]
            self._room_name = self._device.player_name
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

        settings = get_settings()

        # Run blocking SoCo calls in thread pool
        loop = asyncio.get_event_loop()
        try:
            track_info = await loop.run_in_executor(None, device.get_current_track_info)
            transport_info = await loop.run_in_executor(None, device.get_current_transport_info)
        except Exception as e:
            logger.error(f"Error getting Sonos track info: {e}")
            # Reset device to retry discovery next time
            self._device = None
            self._room_name = None
            self._discovery_attempted = False
            return None

        # Check if actually playing
        playback_state = transport_info.get("current_transport_state", "")
        is_playing = playback_state == "PLAYING"

        title = track_info.get("title", "")
        if not title:
            return None

        artist = track_info.get("artist", "") or "Unknown Artist"
        album = track_info.get("album", "") or "Unknown Album"

        # Construct full album art URL from Sonos
        album_art = track_info.get("album_art", "")
        if album_art and not album_art.startswith("http"):
            album_art = f"http://{device.ip_address}:1400{album_art}"

        art_source = "sonos"
        art_source_reason = ""
        original_sonos_url = album_art  # Save for comparison mode

        # Try to get higher-res art from iTunes
        if settings.artwork.prefer_itunes:
            itunes_art, reason = await get_itunes_artwork(artist, album)
            art_source_reason = reason
            if itunes_art:
                album_art = itunes_art
                art_source = "itunes"
                logger.debug(f"Using iTunes artwork for '{title}' ({reason})")
        else:
            art_source_reason = "disabled"

        # Get enhanced queue items with iTunes lookups for debug/comparison modes
        enhanced_queue_items = await self._get_enhanced_queue_items(
            device, settings.artwork.prefetch_count, settings.artwork.prefer_itunes
        )

        # Extract display URLs for backward-compatible prefetching
        upcoming_art_urls = [item["display_url"] for item in enhanced_queue_items]

        return TrackInfo(
            source=self.name,
            title=title,
            artist=artist,
            album=album,
            album_art_url=album_art or None,
            is_playing=is_playing,
            position_ms=self._parse_time(track_info.get("position", "")),
            duration_ms=self._parse_time(track_info.get("duration", "")),
            art_source=art_source,
            art_source_reason=art_source_reason,
            upcoming_art_urls=upcoming_art_urls,
            room_name=self._room_name,
            original_sonos_art_url=original_sonos_url if art_source == "itunes" else None,
            upcoming_queue_items=enhanced_queue_items,
            queue_in_use=len(enhanced_queue_items) > 0,
        )

    async def _get_enhanced_queue_items(
        self, device: SoCo, count: int, prefer_itunes: bool
    ) -> list[dict]:
        """Get queue items with both Sonos and iTunes URLs for debug/comparison modes.

        Returns list of dicts with:
        - sonos_url: Original Sonos artwork URL
        - itunes_url: iTunes high-res URL (if found)
        - title, artist, album: Track metadata
        - has_itunes_match: Whether iTunes art was found
        - display_url: The URL to actually display (iTunes if available, else Sonos)
        - reason: Why iTunes was/wasn't used (e.g., "matched", "no match", "rate limited")
        """
        if count <= 0:
            return []

        loop = asyncio.get_event_loop()
        try:
            queue = await loop.run_in_executor(
                None,
                lambda: device.get_queue(max_items=count, full_album_art_uri=True),
            )
        except Exception as e:
            logger.debug(f"Could not fetch queue: {e}")
            return []

        # Build list of queue items with metadata
        items = []
        for item in queue:
            sonos_url = getattr(item, "album_art_uri", None) or ""
            items.append({
                "sonos_url": sonos_url,
                "itunes_url": None,
                "title": getattr(item, "title", "") or "",
                "artist": getattr(item, "creator", "") or "",
                "album": getattr(item, "album", "") or "",
                "has_itunes_match": False,
                "display_url": sonos_url,
                "reason": "disabled" if not prefer_itunes else "",
            })

        # Do iTunes lookups in parallel if enabled
        if prefer_itunes and items:
            async def lookup_itunes(item: dict) -> None:
                """Look up iTunes art for a single queue item."""
                if item["artist"] and item["album"]:
                    itunes_url, reason = await get_itunes_artwork(item["artist"], item["album"])
                    item["reason"] = reason
                    if itunes_url:
                        item["itunes_url"] = itunes_url
                        item["has_itunes_match"] = True
                        item["display_url"] = itunes_url
                else:
                    item["reason"] = "no metadata"

            await asyncio.gather(*[lookup_itunes(item) for item in items])

        return items

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

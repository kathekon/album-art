"""Playback state management."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Awaitable, Callable

from ..sources.base import TrackInfo


@dataclass
class PlaybackState:
    """Current playback state across all sources."""

    current_track: TrackInfo | None = None
    last_updated: datetime = field(default_factory=datetime.now)

    # Subscribers for state changes
    _subscribers: list[Callable[[TrackInfo | None], Awaitable[None]]] = field(
        default_factory=list, repr=False
    )

    # Grace period for transient disconnects - don't flash "Nothing Playing"
    # on brief network hiccups. Only clear track after consecutive None results.
    _consecutive_none_count: int = field(default=0, repr=False)
    _none_threshold: int = field(default=2, repr=False)  # ~6s at 3s polling interval

    def subscribe(self, callback: Callable[[TrackInfo | None], Awaitable[None]]):
        """Subscribe to state changes."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[TrackInfo | None], Awaitable[None]]):
        """Unsubscribe from state changes."""
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    async def update(self, track: TrackInfo | None):
        """Update the current track and notify subscribers."""
        # Grace period: don't immediately clear track on transient None
        # This prevents jarring "Nothing Playing" flash on brief network hiccups
        if track is None and self.current_track is not None:
            self._consecutive_none_count += 1
            if self._consecutive_none_count < self._none_threshold:
                # Still in grace period - keep current track, don't notify
                return
        else:
            # Got a valid track (or already showing nothing) - reset counter
            self._consecutive_none_count = 0

        # Check if track actually changed
        if self._tracks_equal(self.current_track, track):
            return

        self.current_track = track
        self.last_updated = datetime.now()

        # Notify all subscribers
        await asyncio.gather(
            *[self._safe_notify(callback, track) for callback in self._subscribers],
            return_exceptions=True,
        )

    async def _safe_notify(
        self, callback: Callable[[TrackInfo | None], Awaitable[None]], track: TrackInfo | None
    ):
        """Safely notify a subscriber, catching any exceptions."""
        try:
            await callback(track)
        except Exception:
            pass  # Don't let one bad subscriber break others

    def _tracks_equal(self, a: TrackInfo | None, b: TrackInfo | None) -> bool:
        """Check if two tracks are the same (ignoring position/timestamp)."""
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        return (
            a.source == b.source
            and a.title == b.title
            and a.artist == b.artist
            and a.album == b.album
            and a.is_playing == b.is_playing
        )

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "current_track": self.current_track.to_dict() if self.current_track else None,
            "last_updated": self.last_updated.isoformat(),
        }


# Global singleton
playback_state = PlaybackState()

"""Abstract base class for music sources."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class TrackInfo:
    """Normalized track information from any source."""

    source: str  # "sonos" or "spotify"
    title: str
    artist: str
    album: str
    album_art_url: str | None
    is_playing: bool
    position_ms: int | None = None
    duration_ms: int | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    # For high-res art lookup
    art_source: str = "sonos"  # "sonos", "spotify", or "itunes"
    # For prefetching upcoming artwork
    upcoming_art_urls: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "source": self.source,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "album_art_url": self.album_art_url,
            "is_playing": self.is_playing,
            "position_ms": self.position_ms,
            "duration_ms": self.duration_ms,
            "timestamp": self.timestamp.isoformat(),
            "art_source": self.art_source,
            "upcoming_art_urls": self.upcoming_art_urls,
        }


class MusicSource(ABC):
    """Abstract base class for music source integrations."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the source name."""
        pass

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the source is configured and available."""
        pass

    @abstractmethod
    async def get_current_track(self) -> TrackInfo | None:
        """Get the currently playing track, or None if nothing playing."""
        pass

"""Shared test fixtures and configuration."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from album_art.config import (
    ArtworkConfig,
    PollingConfig,
    ServerConfig,
    Settings,
    SonosConfig,
    SpotifyConfig,
)
from album_art.sources.base import TrackInfo


@pytest.fixture
def sample_track() -> TrackInfo:
    """Create a sample track for testing."""
    return TrackInfo(
        source="sonos",
        title="Test Song",
        artist="Test Artist",
        album="Test Album",
        album_art_url="http://192.168.1.100:1400/album.jpg",
        is_playing=True,
        position_ms=60000,
        duration_ms=180000,
        art_source="sonos",
        upcoming_art_urls=["http://192.168.1.100:1400/next1.jpg"],
        room_name="Living Room",
    )


@pytest.fixture
def sample_track_dict() -> dict:
    """Sample track info as returned by Sonos API."""
    return {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "album_art": "/getaa?s=1&u=sonos://album",
        "position": "1:00",
        "duration": "3:00",
    }


@pytest.fixture
def sample_transport_info() -> dict:
    """Sample transport info as returned by Sonos API."""
    return {"current_transport_state": "PLAYING"}


@pytest.fixture
def test_settings() -> Settings:
    """Create test settings with Sonos enabled."""
    return Settings(
        server=ServerConfig(host="127.0.0.1", port=5174, debug=True),
        polling=PollingConfig(interval=1.0),
        sonos=SonosConfig(enabled=True, ip="192.168.1.100", room=""),
        spotify=SpotifyConfig(enabled=False),
        artwork=ArtworkConfig(prefer_itunes=True, itunes_size=1200, prefetch_count=5),
    )


@pytest.fixture
def test_settings_no_itunes() -> Settings:
    """Create test settings with iTunes disabled."""
    return Settings(
        server=ServerConfig(host="127.0.0.1", port=5174, debug=True),
        polling=PollingConfig(interval=1.0),
        sonos=SonosConfig(enabled=True, ip="192.168.1.100", room=""),
        spotify=SpotifyConfig(enabled=False),
        artwork=ArtworkConfig(prefer_itunes=False, itunes_size=1200, prefetch_count=5),
    )


@pytest.fixture
def mock_settings(test_settings):
    """Patch get_settings to return test settings."""
    with patch("album_art.config.get_settings", return_value=test_settings):
        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch("album_art.sources.itunes.get_settings", return_value=test_settings):
                with patch("album_art.services.poller.get_settings", return_value=test_settings):
                    yield test_settings


@pytest.fixture
def mock_settings_no_itunes(test_settings_no_itunes):
    """Patch get_settings with iTunes disabled."""
    with patch("album_art.config.get_settings", return_value=test_settings_no_itunes):
        with patch("album_art.sources.sonos.get_settings", return_value=test_settings_no_itunes):
            with patch("album_art.sources.itunes.get_settings", return_value=test_settings_no_itunes):
                yield test_settings_no_itunes


@pytest.fixture
def mock_soco_device():
    """Create a mock SoCo device."""
    device = MagicMock()
    device.ip_address = "192.168.1.100"
    device.player_name = "Living Room"
    device.uid = "RINCON_12345"
    device.get_current_track_info.return_value = {
        "title": "Test Song",
        "artist": "Test Artist",
        "album": "Test Album",
        "album_art": "/getaa?s=1&u=sonos://album",
        "position": "1:00",
        "duration": "3:00",
    }
    device.get_current_transport_info.return_value = {
        "current_transport_state": "PLAYING"
    }
    device.get_queue.return_value = []
    return device


class MockQueueItem:
    """Mock Sonos queue item."""

    def __init__(self, album_art_uri: str | None = None):
        self.album_art_uri = album_art_uri


@pytest.fixture
def mock_queue_items():
    """Create mock queue items with album art."""
    return [
        MockQueueItem("http://192.168.1.100:1400/next1.jpg"),
        MockQueueItem("http://192.168.1.100:1400/next2.jpg"),
        MockQueueItem(None),  # Item without art
        MockQueueItem("http://192.168.1.100:1400/next3.jpg"),
    ]

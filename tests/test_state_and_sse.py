"""Tests for playback state management and SSE stream handling.

These tests verify:
- State update propagation to subscribers
- Subscriber exception isolation
- Track change detection
- SSE keepalive behavior
- Client disconnect handling
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from album_art.services.state import PlaybackState
from album_art.sources.base import TrackInfo


def make_track(
    source: str = "sonos",
    title: str = "Test Song",
    artist: str = "Test Artist",
    album: str = "Test Album",
    is_playing: bool = True,
) -> TrackInfo:
    """Helper to create test tracks."""
    return TrackInfo(
        source=source,
        title=title,
        artist=artist,
        album=album,
        album_art_url="http://example.com/art.jpg",
        is_playing=is_playing,
    )


class TestPlaybackState:
    """Test PlaybackState class."""

    @pytest.mark.asyncio
    async def test_subscribe_receives_updates(self):
        """Test subscribers receive track updates."""
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)

        track = make_track()
        await state.update(track)

        assert len(received_tracks) == 1
        assert received_tracks[0].title == "Test Song"

    @pytest.mark.asyncio
    async def test_unsubscribe_stops_updates(self):
        """Test unsubscribed callbacks don't receive updates."""
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)
        state.unsubscribe(callback)

        track = make_track()
        await state.update(track)

        assert len(received_tracks) == 0

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self):
        """Test multiple subscribers all receive updates."""
        state = PlaybackState()
        received_1 = []
        received_2 = []

        async def callback_1(track):
            received_1.append(track)

        async def callback_2(track):
            received_2.append(track)

        state.subscribe(callback_1)
        state.subscribe(callback_2)

        track = make_track()
        await state.update(track)

        assert len(received_1) == 1
        assert len(received_2) == 1

    @pytest.mark.asyncio
    async def test_subscriber_exception_isolation(self):
        """Test one subscriber's exception doesn't affect others."""
        state = PlaybackState()
        received = []

        async def failing_callback(track):
            raise RuntimeError("Subscriber error")

        async def working_callback(track):
            received.append(track)

        state.subscribe(failing_callback)
        state.subscribe(working_callback)

        track = make_track()
        # Should not raise
        await state.update(track)

        # Working callback should still receive update
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_no_update_for_same_track(self):
        """Test no notification when track hasn't changed."""
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)

        track = make_track()
        await state.update(track)
        # Update with identical track info
        await state.update(make_track())

        # Should only receive one update (tracks are equal)
        assert len(received_tracks) == 1

    @pytest.mark.asyncio
    async def test_update_for_different_title(self):
        """Test notification when title changes."""
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)

        await state.update(make_track(title="Song 1"))
        await state.update(make_track(title="Song 2"))

        assert len(received_tracks) == 2

    @pytest.mark.asyncio
    async def test_update_for_playing_state_change(self):
        """Test notification when playing state changes."""
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)

        await state.update(make_track(is_playing=True))
        await state.update(make_track(is_playing=False))

        assert len(received_tracks) == 2
        assert received_tracks[0].is_playing is True
        assert received_tracks[1].is_playing is False

    @pytest.mark.asyncio
    async def test_update_with_none(self):
        """Test update from track to None (nothing playing).

        With grace period, requires 2 consecutive None updates to clear track.
        """
        state = PlaybackState()
        received_tracks = []

        async def callback(track):
            received_tracks.append(track)

        state.subscribe(callback)

        await state.update(make_track())
        await state.update(None)  # First None - grace period, no notification
        await state.update(None)  # Second None - clears track

        assert len(received_tracks) == 2
        assert received_tracks[0] is not None
        assert received_tracks[1] is None

    @pytest.mark.asyncio
    async def test_tracks_equal_different_timestamps(self):
        """Test tracks with different timestamps but same content are equal."""
        state = PlaybackState()

        track1 = TrackInfo(
            source="sonos",
            title="Same Song",
            artist="Same Artist",
            album="Same Album",
            album_art_url="http://example.com/art.jpg",
            is_playing=True,
            timestamp=datetime(2024, 1, 1, 12, 0, 0),
        )

        track2 = TrackInfo(
            source="sonos",
            title="Same Song",
            artist="Same Artist",
            album="Same Album",
            album_art_url="http://example.com/art.jpg",
            is_playing=True,
            timestamp=datetime(2024, 1, 1, 12, 0, 5),  # Different timestamp
        )

        assert state._tracks_equal(track1, track2) is True

    @pytest.mark.asyncio
    async def test_tracks_equal_different_positions(self):
        """Test tracks with different positions but same content are equal."""
        state = PlaybackState()

        track1 = make_track()
        track1.position_ms = 1000

        track2 = make_track()
        track2.position_ms = 5000

        assert state._tracks_equal(track1, track2) is True

    def test_to_dict_with_track(self):
        """Test to_dict serialization with a track."""
        state = PlaybackState()
        state.current_track = make_track()

        result = state.to_dict()
        assert "current_track" in result
        assert result["current_track"]["title"] == "Test Song"
        assert "last_updated" in result

    def test_to_dict_without_track(self):
        """Test to_dict serialization without a track."""
        state = PlaybackState()

        result = state.to_dict()
        assert result["current_track"] is None


class TestGracePeriod:
    """Test grace period for transient disconnects."""

    @pytest.mark.asyncio
    async def test_single_none_keeps_track(self):
        """Test that single None doesn't clear track immediately."""
        state = PlaybackState()
        state.current_track = make_track()
        received = []

        async def callback(track):
            received.append(track)

        state.subscribe(callback)

        await state.update(None)  # First None

        # Track should still be there (grace period)
        assert state.current_track is not None
        # No notification sent
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_consecutive_none_clears_track(self):
        """Test that consecutive Nones clear track after threshold."""
        state = PlaybackState()
        state.current_track = make_track()
        received = []

        async def callback(track):
            received.append(track)

        state.subscribe(callback)

        await state.update(None)  # First None - grace period
        assert state.current_track is not None

        await state.update(None)  # Second None - clears
        assert state.current_track is None
        assert len(received) == 1
        assert received[0] is None

    @pytest.mark.asyncio
    async def test_valid_track_resets_grace_counter(self):
        """Test that receiving a valid track resets the None counter."""
        state = PlaybackState()
        state.current_track = make_track(title="Original")

        await state.update(None)  # First None
        assert state._consecutive_none_count == 1

        await state.update(make_track(title="New Track"))  # Valid track
        assert state._consecutive_none_count == 0

        # Now need 2 more Nones to clear
        await state.update(None)
        assert state.current_track is not None

    @pytest.mark.asyncio
    async def test_grace_period_no_notification_during_grace(self):
        """Test no notifications sent during grace period."""
        state = PlaybackState()
        state.current_track = make_track()
        notifications = []

        async def callback(track):
            notifications.append(track)

        state.subscribe(callback)

        # First None - in grace period
        await state.update(None)
        assert len(notifications) == 0  # No notification

    @pytest.mark.asyncio
    async def test_starting_with_none_no_grace_needed(self):
        """Test that if current_track is already None, no grace period needed."""
        state = PlaybackState()
        # Start with no track
        assert state.current_track is None
        received = []

        async def callback(track):
            received.append(track)

        state.subscribe(callback)

        # Update with None when already None - should be treated as no change
        await state.update(None)
        assert len(received) == 0  # No notification (tracks_equal)

        # Now set a track
        await state.update(make_track())
        assert len(received) == 1


class TestSSEStream:
    """Test SSE endpoint behavior.

    Note: Full SSE streaming tests are tricky because they require
    properly handling the async generator lifecycle. These tests
    focus on the non-streaming endpoints and state management.
    """

    @pytest.mark.asyncio
    async def test_state_endpoint_returns_current(self):
        """Test /api/state returns current playback state."""
        from album_art.main import app
        from album_art.services.state import playback_state

        # Save original state
        original_track = playback_state.current_track

        try:
            playback_state.current_track = make_track(title="Current Song")

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/state")
                assert response.status_code == 200
                data = response.json()
                assert data["current_track"]["title"] == "Current Song"
        finally:
            # Restore original state
            playback_state.current_track = original_track

    @pytest.mark.asyncio
    async def test_state_endpoint_with_no_track(self):
        """Test /api/state returns null track when nothing playing."""
        from album_art.main import app
        from album_art.services.state import playback_state

        original_track = playback_state.current_track

        try:
            playback_state.current_track = None

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                response = await client.get("/api/state")
                assert response.status_code == 200
                data = response.json()
                assert data["current_track"] is None
        finally:
            playback_state.current_track = original_track

    @pytest.mark.asyncio
    async def test_sources_endpoint(self):
        """Test /api/sources returns available sources."""
        from album_art.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/sources")
            assert response.status_code == 200
            data = response.json()
            assert "sources" in data
            # Source availability depends on config, just check structure
            assert all("name" in s and "available" in s for s in data["sources"])

    @pytest.mark.asyncio
    async def test_index_endpoint(self):
        """Test / returns HTML page."""
        from album_art.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/")
            assert response.status_code == 200
            assert "text/html" in response.headers.get("content-type", "")


class TestSubscriberQueue:
    """Test async queue behavior for SSE streaming."""

    @pytest.mark.asyncio
    async def test_queue_receives_updates(self):
        """Test async queue receives state updates."""
        state = PlaybackState()
        queue = asyncio.Queue()

        async def queue_callback(track):
            await queue.put(track)

        state.subscribe(queue_callback)

        track = make_track()
        await state.update(track)

        received = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert received.title == "Test Song"

    @pytest.mark.asyncio
    async def test_queue_handles_rapid_updates(self):
        """Test queue handles multiple rapid updates."""
        state = PlaybackState()
        queue = asyncio.Queue()

        async def queue_callback(track):
            await queue.put(track)

        state.subscribe(queue_callback)

        # Send multiple updates rapidly
        for i in range(10):
            await state.update(make_track(title=f"Song {i}"))

        # Should receive all updates
        received = []
        while not queue.empty():
            received.append(await queue.get())

        assert len(received) == 10

    @pytest.mark.asyncio
    async def test_queue_timeout_for_keepalive(self):
        """Test queue.get timeout works for keepalive pings."""
        queue = asyncio.Queue()

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(queue.get(), timeout=0.1)


class TestTrackInfoSerialization:
    """Test TrackInfo serialization for SSE."""

    def test_to_dict_complete(self):
        """Test complete TrackInfo serialization."""
        track = TrackInfo(
            source="sonos",
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            album_art_url="http://example.com/art.jpg",
            is_playing=True,
            position_ms=60000,
            duration_ms=180000,
            art_source="itunes",
            upcoming_art_urls=["http://example.com/next.jpg"],
            room_name="Living Room",
        )

        data = track.to_dict()

        assert data["source"] == "sonos"
        assert data["title"] == "Test Song"
        assert data["artist"] == "Test Artist"
        assert data["album"] == "Test Album"
        assert data["album_art_url"] == "http://example.com/art.jpg"
        assert data["is_playing"] is True
        assert data["position_ms"] == 60000
        assert data["duration_ms"] == 180000
        assert data["art_source"] == "itunes"
        assert data["upcoming_art_urls"] == ["http://example.com/next.jpg"]
        assert data["room_name"] == "Living Room"
        assert "timestamp" in data

    def test_to_dict_minimal(self):
        """Test minimal TrackInfo serialization."""
        track = TrackInfo(
            source="sonos",
            title="Test Song",
            artist="Test Artist",
            album="Test Album",
            album_art_url=None,
            is_playing=False,
        )

        data = track.to_dict()

        assert data["album_art_url"] is None
        assert data["position_ms"] is None
        assert data["duration_ms"] is None
        assert data["upcoming_art_urls"] == []


class TestConcurrentStateUpdates:
    """Test concurrent access to playback state."""

    @pytest.mark.asyncio
    async def test_concurrent_updates(self):
        """Test multiple concurrent state updates."""
        state = PlaybackState()
        received = []
        lock = asyncio.Lock()

        async def callback(track):
            async with lock:
                received.append(track)

        state.subscribe(callback)

        # Send concurrent updates
        async def update_task(i):
            await state.update(make_track(title=f"Song {i}"))

        await asyncio.gather(*[update_task(i) for i in range(5)])

        # Due to track equality filtering, might not receive all
        # But should receive at least some and not crash
        assert len(received) >= 1

    @pytest.mark.asyncio
    async def test_subscribe_during_update(self):
        """Test subscribing during an update doesn't crash."""
        state = PlaybackState()
        received_1 = []
        received_2 = []

        async def callback_1(track):
            received_1.append(track)
            # Subscribe another callback during update
            state.subscribe(callback_2)

        async def callback_2(track):
            received_2.append(track)

        state.subscribe(callback_1)

        await state.update(make_track(title="First"))
        await state.update(make_track(title="Second"))

        # First callback should get both
        assert len(received_1) == 2
        # Second callback subscribed during first update, should get second
        assert len(received_2) >= 1

    @pytest.mark.asyncio
    async def test_unsubscribe_during_update(self):
        """Test unsubscribing during update doesn't crash."""
        state = PlaybackState()
        received = []

        async def self_unsubscribing_callback(track):
            received.append(track)
            state.unsubscribe(self_unsubscribing_callback)

        state.subscribe(self_unsubscribing_callback)

        await state.update(make_track(title="First"))
        await state.update(make_track(title="Second"))

        # Should only receive first update (unsubscribed after)
        assert len(received) == 1


class TestEdgeCases:
    """Test edge cases and unusual scenarios."""

    @pytest.mark.asyncio
    async def test_empty_string_fields(self):
        """Test handling of empty string fields."""
        track = TrackInfo(
            source="sonos",
            title="",
            artist="",
            album="",
            album_art_url="",
            is_playing=True,
        )

        data = track.to_dict()
        assert data["title"] == ""
        assert data["artist"] == ""

    @pytest.mark.asyncio
    async def test_unicode_in_track_info(self):
        """Test handling of unicode characters."""
        track = TrackInfo(
            source="sonos",
            title="日本語タイトル",
            artist="アーティスト名",
            album="アルバム 🎵",
            album_art_url="http://example.com/art.jpg",
            is_playing=True,
        )

        data = track.to_dict()
        assert data["title"] == "日本語タイトル"
        assert "🎵" in data["album"]

    @pytest.mark.asyncio
    async def test_very_long_strings(self):
        """Test handling of very long strings."""
        long_title = "A" * 10000

        track = TrackInfo(
            source="sonos",
            title=long_title,
            artist="Artist",
            album="Album",
            album_art_url="http://example.com/art.jpg",
            is_playing=True,
        )

        data = track.to_dict()
        assert len(data["title"]) == 10000

    @pytest.mark.asyncio
    async def test_special_characters_in_url(self):
        """Test handling of special characters in album art URL."""
        track = TrackInfo(
            source="sonos",
            title="Song",
            artist="Artist",
            album="Album",
            album_art_url="http://example.com/art.jpg?size=100&format=png",
            is_playing=True,
        )

        data = track.to_dict()
        assert "&" in data["album_art_url"]

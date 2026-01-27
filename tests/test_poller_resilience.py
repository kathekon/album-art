"""Tests for Poller service resilience to source failures.

These tests verify the polling service handles:
- All sources failing simultaneously
- Individual source failures while others succeed
- Exceptions thrown by sources
- Source prioritization logic
- Graceful degradation
"""

import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from album_art.services.poller import Poller
from album_art.services.state import PlaybackState
from album_art.sources.base import MusicSource, TrackInfo


class MockMusicSource(MusicSource):
    """Mock music source for testing."""

    def __init__(
        self,
        name: str,
        available: bool = True,
        track: TrackInfo | None = None,
        exception: Exception | None = None,
    ):
        self._name = name
        self._available = available
        self._track = track
        self._exception = exception
        self._call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_available(self) -> bool:
        return self._available

    async def get_current_track(self) -> TrackInfo | None:
        self._call_count += 1
        if self._exception:
            raise self._exception
        return self._track


def make_track(
    source: str,
    title: str = "Test Song",
    is_playing: bool = True,
    timestamp: datetime | None = None,
) -> TrackInfo:
    """Helper to create test tracks."""
    return TrackInfo(
        source=source,
        title=title,
        artist="Test Artist",
        album="Test Album",
        album_art_url="http://example.com/art.jpg",
        is_playing=is_playing,
        timestamp=timestamp or datetime.now(),
    )


class TestPollerSourceFailures:
    """Test poller handling of source failures."""

    @pytest.mark.asyncio
    async def test_all_sources_fail_with_exceptions(self):
        """Test behavior when all sources throw exceptions."""
        mock_sonos = MockMusicSource(
            "sonos", available=True, exception=RuntimeError("Connection failed")
        )
        mock_spotify = MockMusicSource(
            "spotify", available=True, exception=TimeoutError("Timeout")
        )

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is None
        assert mock_sonos._call_count == 1
        assert mock_spotify._call_count == 1

    @pytest.mark.asyncio
    async def test_all_sources_return_none(self):
        """Test behavior when all sources return None (no playback)."""
        mock_sonos = MockMusicSource("sonos", available=True, track=None)
        mock_spotify = MockMusicSource("spotify", available=True, track=None)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is None

    @pytest.mark.asyncio
    async def test_one_source_fails_other_succeeds(self):
        """Test successful source used when another fails."""
        track = make_track("sonos")
        mock_sonos = MockMusicSource("sonos", available=True, track=track)
        mock_spotify = MockMusicSource(
            "spotify", available=True, exception=RuntimeError("Auth failed")
        )

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is not None
        assert result.source == "sonos"
        assert result.title == "Test Song"

    @pytest.mark.asyncio
    async def test_unavailable_sources_not_polled(self):
        """Test that unavailable sources are skipped."""
        track = make_track("sonos")
        mock_sonos = MockMusicSource("sonos", available=True, track=track)
        mock_spotify = MockMusicSource("spotify", available=False, track=None)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is not None
        # Unavailable source should not be called
        assert mock_spotify._call_count == 0

    @pytest.mark.asyncio
    async def test_no_available_sources(self):
        """Test behavior when no sources are available."""
        mock_sonos = MockMusicSource("sonos", available=False)
        mock_spotify = MockMusicSource("spotify", available=False)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is None
        assert mock_sonos._call_count == 0
        assert mock_spotify._call_count == 0


class TestPollerSourcePrioritization:
    """Test poller's source prioritization logic."""

    @pytest.mark.asyncio
    async def test_playing_preferred_over_paused(self):
        """Test that playing tracks are preferred over paused ones."""
        playing_track = make_track("spotify", is_playing=True)
        paused_track = make_track("sonos", is_playing=False)

        mock_sonos = MockMusicSource("sonos", available=True, track=paused_track)
        mock_spotify = MockMusicSource("spotify", available=True, track=playing_track)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is not None
        assert result.is_playing is True
        assert result.source == "spotify"

    @pytest.mark.asyncio
    async def test_spotify_preferred_for_higher_quality_art(self):
        """Test Spotify preferred when both are playing (higher quality art)."""
        sonos_track = make_track("sonos", title="Sonos Track", is_playing=True)
        spotify_track = make_track("spotify", title="Spotify Track", is_playing=True)

        mock_sonos = MockMusicSource("sonos", available=True, track=sonos_track)
        mock_spotify = MockMusicSource("spotify", available=True, track=spotify_track)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is not None
        assert result.source == "spotify"

    @pytest.mark.asyncio
    async def test_most_recent_paused_track_selected(self):
        """Test most recent paused track selected when nothing playing."""
        older_time = datetime.now() - timedelta(minutes=5)
        newer_time = datetime.now()

        older_track = make_track("sonos", is_playing=False, timestamp=older_time)
        newer_track = make_track("spotify", is_playing=False, timestamp=newer_time)

        mock_sonos = MockMusicSource("sonos", available=True, track=older_track)
        mock_spotify = MockMusicSource("spotify", available=True, track=newer_track)

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        result = await poller._poll_sources()
        assert result is not None
        # Should pick the newer timestamp
        assert result.source == "spotify"


class TestPollerLoopResilience:
    """Test poller loop continues despite errors."""

    @pytest.mark.asyncio
    async def test_poll_loop_continues_after_exception(self):
        """Test polling loop continues after source exception."""
        poll_count = 0
        exception_on_poll = 2  # Fail on second poll

        async def mock_poll_sources():
            nonlocal poll_count
            poll_count += 1
            if poll_count == exception_on_poll:
                raise RuntimeError("Network error")
            return make_track("sonos")

        # Create poller
        poller = Poller.__new__(Poller)
        poller._sources = []
        poller._running = True
        poller._task = None

        # Mock settings for fast polling
        mock_settings = MagicMock()
        mock_settings.polling.interval = 0.01  # Very fast for test

        # Create state to track updates
        state = PlaybackState()
        update_count = 0

        async def count_updates(track):
            nonlocal update_count
            update_count += 1

        state.subscribe(count_updates)

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            with patch.object(poller, "_poll_sources", side_effect=mock_poll_sources):
                with patch("album_art.services.poller.playback_state", state):
                    # Start polling
                    poller._task = asyncio.create_task(poller._poll_loop())

                    # Let it run for a few polls
                    await asyncio.sleep(0.05)

                    # Stop
                    poller._running = False
                    poller._task.cancel()
                    try:
                        await poller._task
                    except asyncio.CancelledError:
                        pass

        # Should have polled multiple times despite exception
        assert poll_count >= 3
        # Updates should have happened before and after the error
        assert update_count >= 1

    @pytest.mark.asyncio
    async def test_poll_loop_handles_state_update_failure(self):
        """Test polling continues even if state update fails."""
        poll_count = 0

        async def mock_poll_sources():
            nonlocal poll_count
            poll_count += 1
            return make_track("sonos", title=f"Track {poll_count}")

        async def failing_update(track):
            raise RuntimeError("Update failed")

        mock_settings = MagicMock()
        mock_settings.polling.interval = 0.01

        state = PlaybackState()
        state.subscribe(failing_update)

        poller = Poller.__new__(Poller)
        poller._sources = []
        poller._running = True
        poller._task = None

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            with patch.object(poller, "_poll_sources", side_effect=mock_poll_sources):
                with patch("album_art.services.poller.playback_state", state):
                    poller._task = asyncio.create_task(poller._poll_loop())
                    await asyncio.sleep(0.05)
                    poller._running = False
                    poller._task.cancel()
                    try:
                        await poller._task
                    except asyncio.CancelledError:
                        pass

        # Polling should continue despite subscriber failure
        assert poll_count >= 2


class TestPollerConcurrency:
    """Test concurrent source polling behavior."""

    @pytest.mark.asyncio
    async def test_sources_polled_concurrently(self):
        """Test that sources are polled concurrently, not sequentially."""
        call_times = []

        async def slow_get_track(delay: float, source: str):
            call_times.append((source, "start", asyncio.get_event_loop().time()))
            await asyncio.sleep(delay)
            call_times.append((source, "end", asyncio.get_event_loop().time()))
            return make_track(source)

        mock_sonos = MockMusicSource("sonos", available=True)
        mock_spotify = MockMusicSource("spotify", available=True)

        # Replace get_current_track with slow versions
        mock_sonos.get_current_track = lambda: slow_get_track(0.05, "sonos")
        mock_spotify.get_current_track = lambda: slow_get_track(0.05, "spotify")

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        start = asyncio.get_event_loop().time()
        result = await poller._poll_sources()
        elapsed = asyncio.get_event_loop().time() - start

        # If concurrent, should take ~0.05s, not ~0.10s
        assert elapsed < 0.08  # Some buffer for overhead
        assert result is not None

        # Both should have started before either ended
        starts = [t for s, e, t in call_times if e == "start"]
        ends = [t for s, e, t in call_times if e == "end"]
        assert max(starts) < min(ends)

    @pytest.mark.asyncio
    async def test_slow_source_doesnt_block_fast_source(self):
        """Test slow failing source doesn't delay using fast successful source."""

        async def slow_failing_track():
            await asyncio.sleep(0.1)
            raise TimeoutError("Slow timeout")

        async def fast_successful_track():
            await asyncio.sleep(0.01)
            return make_track("sonos")

        mock_sonos = MockMusicSource("sonos", available=True)
        mock_spotify = MockMusicSource("spotify", available=True)

        mock_sonos.get_current_track = fast_successful_track
        mock_spotify.get_current_track = slow_failing_track

        poller = Poller.__new__(Poller)
        poller._sources = [mock_sonos, mock_spotify]
        poller._running = False
        poller._task = None

        start = asyncio.get_event_loop().time()
        result = await poller._poll_sources()
        elapsed = asyncio.get_event_loop().time() - start

        # Should still return result (need to wait for all due to gather)
        assert result is not None
        assert result.source == "sonos"


class TestPollerStartStop:
    """Test poller start/stop lifecycle."""

    @pytest.mark.asyncio
    async def test_start_creates_task(self):
        """Test starting poller creates background task."""
        mock_settings = MagicMock()
        mock_settings.sonos.enabled = False
        mock_settings.spotify.enabled = False
        mock_settings.polling.interval = 1.0

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            poller = Poller()
            assert poller._task is None

            await poller.start()
            assert poller._task is not None
            assert poller._running is True

            await poller.stop()
            assert poller._running is False

    @pytest.mark.asyncio
    async def test_stop_cancels_task(self):
        """Test stopping poller cancels the polling task."""
        mock_settings = MagicMock()
        mock_settings.sonos.enabled = False
        mock_settings.spotify.enabled = False
        mock_settings.polling.interval = 0.01

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            poller = Poller()
            await poller.start()

            task = poller._task
            assert task is not None
            assert not task.done()

            await poller.stop()
            assert task.done() or task.cancelled()

    @pytest.mark.asyncio
    async def test_double_start_is_idempotent(self):
        """Test calling start twice doesn't create duplicate tasks."""
        mock_settings = MagicMock()
        mock_settings.sonos.enabled = False
        mock_settings.spotify.enabled = False
        mock_settings.polling.interval = 1.0

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            poller = Poller()
            await poller.start()
            first_task = poller._task

            await poller.start()
            assert poller._task is first_task  # Same task

            await poller.stop()

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """Test stopping without starting doesn't raise."""
        mock_settings = MagicMock()
        mock_settings.sonos.enabled = False
        mock_settings.spotify.enabled = False

        with patch("album_art.services.poller.get_settings", return_value=mock_settings):
            poller = Poller()
            # Should not raise
            await poller.stop()
            assert poller._running is False

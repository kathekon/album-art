"""Tests for Sonos connectivity and network failure scenarios.

These tests verify the application handles various network issues gracefully:
- Device unreachable (connection timeout, refused)
- Device disconnects during polling
- Auto-discovery timeout/failure
- Invalid device at configured IP
- Queue fetch failures
"""

import asyncio
import socket
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

import pytest
import soco
from soco import SoCo
from soco.exceptions import SoCoException

from album_art.sources.sonos import SonosSource


class TestSonosDeviceConnection:
    """Test Sonos device connection scenarios."""

    @pytest.mark.asyncio
    async def test_device_unreachable_connection_refused(self, mock_settings):
        """Test behavior when Sonos device refuses connection (device offline)."""
        with patch("album_art.sources.sonos.SoCo") as mock_soco_class:
            # Simulate connection refused error
            mock_soco_class.side_effect = OSError(
                111, "Connection refused"
            )

            # Also mock discovery to return nothing (so no fallback)
            with patch("album_art.sources.sonos.soco.discover", return_value=None):
                source = SonosSource()
                assert not source.is_available
                track = await source.get_current_track()
                assert track is None

    @pytest.mark.asyncio
    async def test_device_unreachable_timeout(self, mock_settings):
        """Test behavior when Sonos device times out (network unreachable)."""
        with patch("album_art.sources.sonos.SoCo") as mock_soco_class:
            # Simulate socket timeout
            mock_soco_class.side_effect = socket.timeout("Connection timed out")

            # Also mock discovery to return nothing (so no fallback)
            with patch("album_art.sources.sonos.soco.discover", return_value=None):
                source = SonosSource()
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_device_unreachable_host_unreachable(self, mock_settings):
        """Test behavior when host is unreachable (network partition)."""
        with patch("album_art.sources.sonos.SoCo") as mock_soco_class:
            # Simulate no route to host
            mock_soco_class.side_effect = OSError(113, "No route to host")

            # Also mock discovery to return nothing
            with patch("album_art.sources.sonos.soco.discover", return_value=None):
                source = SonosSource()
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_invalid_device_at_ip(self, mock_settings):
        """Test behavior when IP points to non-Sonos device (validation fails)."""

        # Create a fake device class that raises on uid access
        class FakeNonSonosDevice:
            player_name = "Some Router"

            @property
            def uid(self):
                raise AttributeError("Device has no 'uid' attribute")

        with patch("album_art.sources.sonos.SoCo", return_value=FakeNonSonosDevice()):
            # Also mock discovery to return nothing (so no fallback)
            with patch("album_art.sources.sonos.soco.discover", return_value=None):
                source = SonosSource()
                # Should fail validation since uid access fails
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_valid_device_connection(self, mock_settings, mock_soco_device):
        """Test successful connection to valid Sonos device."""
        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            source = SonosSource()
            assert source.is_available
            assert source._room_name == "Living Room"


class TestSonosPollingFailures:
    """Test failures during active polling."""

    @pytest.mark.asyncio
    async def test_disconnect_during_track_info_fetch(self, mock_settings, mock_soco_device):
        """Test device disconnects while fetching track info."""
        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            source = SonosSource()
            assert source.is_available

            # Now simulate disconnect on next poll
            mock_soco_device.get_current_track_info.side_effect = OSError(
                104, "Connection reset by peer"
            )

            track = await source.get_current_track()
            assert track is None

            # Verify device state was reset for retry
            assert source._device is None
            assert source._discovery_attempted is False

    @pytest.mark.asyncio
    async def test_disconnect_during_transport_info_fetch(
        self, mock_settings, mock_soco_device
    ):
        """Test device disconnects while fetching transport info."""
        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            source = SonosSource()
            assert source.is_available

            # Track info succeeds but transport info fails
            mock_soco_device.get_current_transport_info.side_effect = socket.timeout(
                "Read timed out"
            )

            track = await source.get_current_track()
            assert track is None
            assert source._device is None

    @pytest.mark.asyncio
    async def test_soco_library_exception(self, mock_settings, mock_soco_device):
        """Test SoCo library-specific exceptions are handled."""
        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            source = SonosSource()
            assert source.is_available

            # SoCo library can raise SoCoException for various issues
            mock_soco_device.get_current_track_info.side_effect = SoCoException(
                "UPnP Error: Action failed"
            )

            track = await source.get_current_track()
            assert track is None
            assert source._device is None

    @pytest.mark.asyncio
    async def test_intermittent_failure_recovery(self, mock_settings, mock_soco_device):
        """Test recovery from intermittent network failures."""
        call_count = 0

        def intermittent_failure():
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise OSError(104, "Connection reset by peer")
            return {
                "title": "Test Song",
                "artist": "Test Artist",
                "album": "Test Album",
                "album_art": "/art.jpg",
                "position": "1:00",
                "duration": "3:00",
            }

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                mock_soco_device.get_current_track_info.side_effect = intermittent_failure

                # First call succeeds
                track1 = await source.get_current_track()
                assert track1 is not None
                assert track1.title == "Test Song"

                # Second call fails (intermittent)
                track2 = await source.get_current_track()
                assert track2 is None

                # Device was reset, would need to reconnect
                assert source._device is None


class TestSonosAutoDiscovery:
    """Test Sonos auto-discovery scenarios."""

    @pytest.mark.asyncio
    async def test_discovery_timeout(self, test_settings):
        """Test behavior when Sonos discovery times out."""
        test_settings.sonos.ip = ""  # Force discovery

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch("album_art.sources.sonos.soco.discover", return_value=None):
                source = SonosSource()
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_discovery_no_devices_found(self, test_settings):
        """Test behavior when discovery finds no devices."""
        test_settings.sonos.ip = ""

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch("album_art.sources.sonos.soco.discover", return_value=[]):
                source = SonosSource()
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_discovery_network_error(self, test_settings):
        """Test behavior when discovery encounters network error."""
        test_settings.sonos.ip = ""

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch(
                "album_art.sources.sonos.soco.discover",
                side_effect=OSError("Network is unreachable"),
            ):
                source = SonosSource()
                assert not source.is_available

    @pytest.mark.asyncio
    async def test_discovery_finds_device(self, test_settings, mock_soco_device):
        """Test successful auto-discovery."""
        test_settings.sonos.ip = ""

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch(
                "album_art.sources.sonos.soco.discover", return_value=[mock_soco_device]
            ):
                source = SonosSource()
                assert source.is_available
                assert source._room_name == "Living Room"

    @pytest.mark.asyncio
    async def test_discovery_room_filter_not_found(self, test_settings, mock_soco_device):
        """Test discovery with room filter that doesn't match."""
        test_settings.sonos.ip = ""
        test_settings.sonos.room = "Bedroom"  # Different from "Living Room"

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch(
                "album_art.sources.sonos.soco.discover", return_value=[mock_soco_device]
            ):
                source = SonosSource()
                # Room filter didn't match, but should fall back to first device
                assert source.is_available

    @pytest.mark.asyncio
    async def test_fallback_to_discovery_after_ip_fails(self, test_settings, mock_soco_device):
        """Test fallback to discovery when configured IP fails."""
        test_settings.sonos.ip = "192.168.1.99"  # Bad IP

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch("album_art.sources.sonos.SoCo") as mock_soco_class:
                # First call with bad IP fails
                mock_soco_class.side_effect = [
                    OSError("Connection refused"),
                    mock_soco_device,  # Discovery would return this
                ]
                with patch(
                    "album_art.sources.sonos.soco.discover", return_value=[mock_soco_device]
                ):
                    source = SonosSource()
                    # Should fall back to discovery
                    assert source.is_available


class TestSonosQueueFetch:
    """Test Sonos queue fetching for prefetch feature."""

    @pytest.mark.asyncio
    async def test_queue_fetch_timeout(self, mock_settings, mock_soco_device):
        """Test queue fetch gracefully handles timeout."""
        mock_soco_device.get_queue.side_effect = socket.timeout("Read timed out")

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                track = await source.get_current_track()

                # Track info should still be returned
                assert track is not None
                # But upcoming_art_urls should be empty due to queue failure
                assert track.upcoming_art_urls == []

    @pytest.mark.asyncio
    async def test_queue_fetch_connection_error(self, mock_settings, mock_soco_device):
        """Test queue fetch handles connection errors."""
        mock_soco_device.get_queue.side_effect = OSError("Connection reset")

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                track = await source.get_current_track()

                assert track is not None
                assert track.upcoming_art_urls == []

    @pytest.mark.asyncio
    async def test_queue_fetch_success(self, mock_settings, mock_soco_device, mock_queue_items):
        """Test successful queue fetch returns artwork URLs."""
        mock_soco_device.get_queue.return_value = mock_queue_items

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                track = await source.get_current_track()

                assert track is not None
                # Should have 3 URLs (one item had None)
                assert len(track.upcoming_art_urls) == 3

    @pytest.mark.asyncio
    async def test_queue_fetch_disabled(self, test_settings, mock_soco_device):
        """Test queue prefetch is skipped when prefetch_count is 0."""
        test_settings.artwork.prefetch_count = 0

        with patch("album_art.sources.sonos.get_settings", return_value=test_settings):
            with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
                with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                    source = SonosSource()
                    track = await source.get_current_track()

                    assert track is not None
                    assert track.upcoming_art_urls == []
                    # Queue should not be called at all
                    mock_soco_device.get_queue.assert_not_called()


class TestSonosPlaybackState:
    """Test correct handling of playback states."""

    @pytest.mark.asyncio
    async def test_paused_state(self, mock_settings, mock_soco_device):
        """Test handling of PAUSED_PLAYBACK state."""
        mock_soco_device.get_current_transport_info.return_value = {
            "current_transport_state": "PAUSED_PLAYBACK"
        }

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                track = await source.get_current_track()

                assert track is not None
                assert track.is_playing is False

    @pytest.mark.asyncio
    async def test_stopped_state(self, mock_settings, mock_soco_device):
        """Test handling of STOPPED state."""
        mock_soco_device.get_current_transport_info.return_value = {
            "current_transport_state": "STOPPED"
        }

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            with patch("album_art.sources.sonos.get_itunes_artwork", return_value=None):
                source = SonosSource()
                track = await source.get_current_track()

                assert track is not None
                assert track.is_playing is False

    @pytest.mark.asyncio
    async def test_no_track_playing(self, mock_settings, mock_soco_device):
        """Test handling when no track is playing (empty title)."""
        mock_soco_device.get_current_track_info.return_value = {
            "title": "",
            "artist": "",
            "album": "",
            "album_art": "",
            "position": "",
            "duration": "",
        }

        with patch("album_art.sources.sonos.SoCo", return_value=mock_soco_device):
            source = SonosSource()
            track = await source.get_current_track()

            # Should return None when title is empty
            assert track is None

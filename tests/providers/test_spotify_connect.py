"""Tests for the Spotify Connect plugin provider.

Covers:
- Timestamp-based echo window suppression for inbound volume_changed events
- Skipping outbound volume while processing an inbound volume_changed event
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

from music_assistant_models.enums import PlayerType

from music_assistant.providers.spotify_connect import (
    _VOLUME_ECHO_SUPPRESS_WINDOW,
    SpotifyConnectProvider,
)


def _make_volume_changed_request(raw_volume: int = 32768) -> MagicMock:
    """Create a mock aiohttp Request carrying a volume_changed event."""
    req = MagicMock()
    req.json = AsyncMock(return_value={"event": "volume_changed", "volume": str(raw_volume)})
    return req


def _make_mock_spotify_provider(
    in_use_by: str = "player1",
    last_outbound_time: float | None = None,
) -> MagicMock:
    """Create a mock standing in for SpotifyConnectProvider.

    Provides just enough attributes for _handle_custom_webservice's
    volume_changed branch to execute without errors.
    """
    prov = MagicMock()
    prov._last_session_connected_time = 0.0
    prov._last_outbound_volume_time = last_outbound_time if last_outbound_time is not None else 0.0
    prov._processing_inbound_volume = False
    prov._source_details.in_use_by = in_use_by
    prov._connected_spotify_username = "testuser"
    prov.mass.players.cmd_volume_set = AsyncMock()
    prov.mass.players.cmd_group_volume = AsyncMock()
    prov.mass.players.trigger_player_update = MagicMock()
    mock_player = MagicMock()
    mock_player.state.type = PlayerType.PLAYER
    mock_player.state.group_members = []
    prov.mass.players.get_player.return_value = mock_player
    return prov


class TestSpotifyEchoWindowSuppression:
    """Test the timestamp-based echo window in SpotifyConnectProvider."""

    async def test_inbound_suppressed_within_echo_window(self) -> None:
        """Inbound volume_changed is suppressed within the echo window."""
        mock_self = _make_mock_spotify_provider(
            last_outbound_time=time.monotonic(),
        )
        request = _make_volume_changed_request(raw_volume=32768)

        await SpotifyConnectProvider._handle_custom_webservice(mock_self, request)

        mock_self.mass.players.cmd_volume_set.assert_not_awaited()
        mock_self.mass.players.cmd_group_volume.assert_not_awaited()

    async def test_inbound_accepted_outside_echo_window(self) -> None:
        """Inbound volume_changed is accepted after the echo window expires."""
        mock_self = _make_mock_spotify_provider(
            last_outbound_time=time.monotonic() - _VOLUME_ECHO_SUPPRESS_WINDOW - 1,
        )
        request = _make_volume_changed_request(raw_volume=32768)

        await SpotifyConnectProvider._handle_custom_webservice(mock_self, request)

        mock_self.mass.players.cmd_volume_set.assert_awaited_once()

    async def test_rapid_drags_suppressed(self) -> None:
        """Multiple echoes during rapid slider drags are all suppressed."""
        mock_self = _make_mock_spotify_provider(
            last_outbound_time=time.monotonic(),
        )

        for raw_vol in (20000, 25000, 30000):
            request = _make_volume_changed_request(raw_volume=raw_vol)
            await SpotifyConnectProvider._handle_custom_webservice(mock_self, request)

        mock_self.mass.players.cmd_volume_set.assert_not_awaited()
        mock_self.mass.players.cmd_group_volume.assert_not_awaited()


class TestSpotifyOnVolumeProcessingInboundFlag:
    """Test _on_volume skips outbound while _processing_inbound_volume is set."""

    async def test_on_volume_skipped_when_processing_inbound(self) -> None:
        """Outbound Spotify volume is not sent while processing an inbound change."""
        mock_self = MagicMock()
        mock_self._processing_inbound_volume = True
        mock_self._spotify_provider = MagicMock()
        mock_self._spotify_provider.throttler.bypass = MagicMock()
        mock_self._spotify_provider.throttler.bypass.return_value.__aenter__ = AsyncMock()
        mock_self._spotify_provider.throttler.bypass.return_value.__aexit__ = AsyncMock()
        mock_self._spotify_provider._put_data = AsyncMock()
        mock_self._source_details = MagicMock()
        mock_self._source_details.in_use_by = "p1"
        mock_self.logger = MagicMock()

        await SpotifyConnectProvider._on_volume(mock_self, 50)

        mock_self._spotify_provider._put_data.assert_not_awaited()

    async def test_on_volume_proceeds_when_not_processing_inbound(self) -> None:
        """Outbound Spotify volume is sent when not processing an inbound change."""
        mock_self = MagicMock()
        mock_self._processing_inbound_volume = False
        mock_self._spotify_provider = MagicMock()
        mock_self._spotify_provider.throttler.bypass = MagicMock()
        mock_self._spotify_provider.throttler.bypass.return_value.__aenter__ = AsyncMock()
        mock_self._spotify_provider.throttler.bypass.return_value.__aexit__ = AsyncMock()
        mock_self._spotify_provider._put_data = AsyncMock()
        mock_self._source_details = MagicMock()
        mock_self._source_details.in_use_by = "p1"
        mock_self.logger = MagicMock()

        await SpotifyConnectProvider._on_volume(mock_self, 50)

        mock_self._spotify_provider._put_data.assert_awaited_once()

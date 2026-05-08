"""Tests for plugin volume feedback loop fix.

Covers:
- Reactive plugin volume callback via signal_player_state_update
- Optimistic volume state coherence for group_volume
- Standalone player plugin callback behavior
- Inbound Spotify volume routing through cmd_group_volume
- Echo suppression via zero-delta convergence
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from music_assistant_models.enums import PlayerType

from music_assistant.controllers.players import PlayerController
from music_assistant.helpers.throttle_retry import Throttler
from music_assistant.models.plugin import PluginSource
from tests.common import MockPlayer, MockProvider

RegisterPlayer = Callable[..., MockPlayer]


@pytest.fixture
def mock_mass() -> MagicMock:
    """Create a mock MusicAssistant instance."""
    mass = MagicMock()
    mass.closing = False
    mass.loop = None
    mass.config = MagicMock()
    mass.config.get = MagicMock(return_value=[])
    mass.config.get_raw_player_config_value = MagicMock(return_value="auto")
    mass.config.get_raw_core_config_value = MagicMock(return_value="GLOBAL")
    mass.config.set = MagicMock()
    mass.signal_event = MagicMock()
    mass.get_providers = MagicMock(return_value=[])
    mass.call_later = MagicMock()
    mass.verify_event_loop_thread = MagicMock()
    return mass


@pytest.fixture
def controller(mock_mass: MagicMock) -> PlayerController:
    """Create a PlayerController wired to mock_mass."""
    ctrl = PlayerController(mock_mass)
    mock_mass.players = ctrl
    return ctrl


@pytest.fixture
def provider(mock_mass: MagicMock) -> MockProvider:
    """Create a MockProvider with a players list."""
    prov = MockProvider("test", mass=mock_mass)
    prov.players = []  # type: ignore[attr-defined]
    return prov


@pytest.fixture
def register_player(controller: PlayerController, provider: MockProvider) -> RegisterPlayer:
    """Create, register, and initialize a player."""

    def _register(
        player_id: str,
        name: str,
        volume: int = 50,
        player_type: PlayerType = PlayerType.PLAYER,
    ) -> MockPlayer:
        player = MockPlayer(provider, player_id, name, player_type=player_type)
        player._attr_volume_level = volume
        controller._players[player_id] = player
        controller._player_throttlers[player_id] = Throttler(1, 0.05)
        provider.players.append(player)  # type: ignore[attr-defined]
        player.update_state(signal_event=False)
        return player

    return _register


def _make_plugin_source(
    source_id: str, in_use_by: str, on_volume: AsyncMock | None = None
) -> PluginSource:
    """Create a PluginSource with the given properties."""
    return PluginSource(
        id=source_id,
        name=source_id,
        in_use_by=in_use_by,
        on_volume=on_volume or AsyncMock(),
    )


def _get_plugin_volume_calls(
    mock_mass: MagicMock, task_prefix: str = "plugin_volume_"
) -> list[Any]:
    """Extract plugin volume call_later calls from mock_mass."""
    return [
        c
        for c in mock_mass.call_later.call_args_list
        if c.kwargs.get("task_id", "").startswith(task_prefix)
    ]


class TestReactivePluginVolumeCallback:
    """Test that plugin on_volume fires reactively from signal_player_state_update."""

    def test_callback_fires_on_group_volume_change(
        self,
        controller: PlayerController,
        mock_mass: MagicMock,
        register_player: RegisterPlayer,
    ) -> None:
        """Plugin on_volume fires with the correct group average when a child volume changes."""
        leader = register_player("leader", "Leader", volume=50)
        child = register_player("child", "Child", volume=50)

        leader._attr_group_members = ["leader", "child"]
        leader.update_state(signal_event=False)

        on_volume = AsyncMock()
        source = _make_plugin_source("spotify", in_use_by="leader", on_volume=on_volume)

        child._attr_volume_level = 70
        child.update_state(signal_event=False)

        mock_mass.call_later.reset_mock()
        with patch.object(controller, "get_plugin_sources", return_value=[source]):
            leader.update_state()

        plugin_calls = _get_plugin_volume_calls(mock_mass, "plugin_volume_leader")
        assert len(plugin_calls) > 0, "Expected plugin volume callback to be scheduled"
        last_call = plugin_calls[-1]
        assert last_call.args[0] == 0.25
        assert last_call.args[1] is on_volume
        assert last_call.args[2] == 60

    def test_callback_does_not_fire_for_non_owning_player(
        self,
        controller: PlayerController,
        mock_mass: MagicMock,
        register_player: RegisterPlayer,
    ) -> None:
        """Plugin on_volume does NOT fire for a child that merely inherits active_source."""
        register_player("child", "Child", volume=50)

        on_volume = AsyncMock()
        source = _make_plugin_source("spotify", in_use_by="leader", on_volume=on_volume)

        mock_mass.call_later.reset_mock()

        child = controller.get_player("child")
        assert child is not None
        with patch.object(controller, "get_plugin_sources", return_value=[source]):
            child._attr_volume_level = 60
            child.update_state()

        assert len(_get_plugin_volume_calls(mock_mass)) == 0, (
            "Plugin callback should not fire for non-owning player"
        )

    def test_callback_not_fired_when_group_volume_unchanged(
        self,
        controller: PlayerController,
        mock_mass: MagicMock,
        register_player: RegisterPlayer,
    ) -> None:
        """Plugin on_volume does NOT fire if group_volume did not change."""
        leader = register_player("leader", "Leader", volume=50)

        on_volume = AsyncMock()
        source = _make_plugin_source("spotify", in_use_by="leader", on_volume=on_volume)

        # Call update_state twice to stabilize (MagicMock fields in
        # current_media create new objects each access, causing spurious diffs)
        with patch.object(controller, "get_plugin_sources", return_value=[source]):
            leader.update_state(signal_event=False)
            mock_mass.call_later.reset_mock()
            leader.update_state(force_update=True)

        assert len(_get_plugin_volume_calls(mock_mass)) == 0, (
            "Plugin callback should not fire when group_volume is unchanged"
        )


class TestOptimisticVolumeCoherence:
    """Test group_volume coherence after volume commands."""

    async def test_group_volume_coherent_after_set_group_volume(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """After set_group_volume, group_volume reflects the new child volumes immediately."""
        leader = register_player("leader", "Leader", volume=40)
        register_player("child1", "Child 1", volume=40)
        register_player("child2", "Child 2", volume=40)

        leader._attr_group_members = ["leader", "child1", "child2"]
        leader.update_state(signal_event=False)

        for p in [controller.get_player(pid) for pid in ("leader", "child1", "child2")]:
            assert p is not None
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        await controller.set_group_volume(leader, 60)

        assert leader.state.group_volume == 60

    async def test_echo_produces_zero_delta(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """After set_group_volume(60), a subsequent set_group_volume(60) echo produces delta=0."""
        leader = register_player("leader", "Leader", volume=50)
        child1 = register_player("child1", "Child 1", volume=50)

        leader._attr_group_members = ["leader", "child1"]
        leader.update_state(signal_event=False)

        for p in [leader, child1]:
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        await controller.set_group_volume(leader, 60)
        assert leader.state.group_volume == 60

        leader.volume_set.reset_mock()  # type: ignore[attr-defined]
        child1.volume_set.reset_mock()  # type: ignore[attr-defined]

        await controller.set_group_volume(leader, 60)

        leader.volume_set.assert_awaited_once_with(60)  # type: ignore[attr-defined]
        child1.volume_set.assert_awaited_once_with(60)  # type: ignore[attr-defined]


class TestInlinePluginCallbackRemoved:
    """Test that _handle_cmd_volume_set no longer fires inline plugin callbacks."""

    async def test_no_inline_plugin_callback(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """_handle_cmd_volume_set does NOT call plugin on_volume inline."""
        player = register_player("p1", "Player 1", volume=50)
        player.volume_set = AsyncMock()  # type: ignore[method-assign]

        on_volume = AsyncMock()
        source = _make_plugin_source("spotify", in_use_by="p1", on_volume=on_volume)

        with patch.object(controller, "get_plugin_sources", return_value=[source]):
            await controller._handle_cmd_volume_set("p1", 70)

        on_volume.assert_not_awaited()


class TestInboundVolumeGroupRouting:
    """Test that inbound volume for group players routes through cmd_group_volume."""

    async def test_group_player_routes_to_cmd_group_volume(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """Inbound volume for a GROUP player routes through cmd_group_volume."""
        group = register_player("group1", "Group", volume=50, player_type=PlayerType.GROUP)
        group._attr_group_members = ["child1", "child2"]
        group.update_state(signal_event=False)

        for pid in ("child1", "child2"):
            p = register_player(pid, pid, volume=50)
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        with patch.object(controller, "cmd_group_volume", new_callable=AsyncMock) as mock_gv:
            await controller.cmd_volume_set("group1", 60)
            mock_gv.assert_awaited_once_with("group1", 60)

    async def test_ad_hoc_sync_leader_with_group_members(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """Inbound volume for an ad-hoc sync leader (PLAYER with group_members) gets correct treatment."""
        leader = register_player("leader", "Leader", volume=50)
        child1 = register_player("child1", "Child 1", volume=50)

        leader._attr_group_members = ["leader", "child1"]
        leader.update_state(signal_event=False)

        for p in [leader, child1]:
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        await controller.set_group_volume(leader, 60)

        assert leader.state.group_volume == 60
        leader.volume_set.assert_awaited_once_with(60)  # type: ignore[attr-defined]
        child1.volume_set.assert_awaited_once_with(60)  # type: ignore[attr-defined]

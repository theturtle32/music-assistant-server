"""Tests for the group volume algorithm (set_group_volume / additive-delta).

Covers:
- Clamping behavior at volume boundaries (0 and 100)
- Expected future behavior: commanded group_volume should be respected
  even when clamping would cause the derived average to diverge. The excess
  volume delta from clamping should be redistributed across the non-clamped
  players in order for the additive-delta algorithm to be bidirectionally
  correct.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import AsyncMock, MagicMock

import pytest
from music_assistant_models.enums import PlayerType

from music_assistant.controllers.players import PlayerController
from music_assistant.helpers.throttle_retry import Throttler
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


class TestGroupVolumeCommandedValue:
    """Tests for group_volume respecting commanded values.

    The current additive-delta algorithm recomputes group_volume as the average
    of children's volumes after each set_group_volume call. When clamping occurs
    (a child hits 0 or 100), the recomputed average diverges from the commanded
    target -- causing the UI slider to snap back. These tests document the
    expected behavior for a future fix.
    """

    async def test_group_volume_matches_target_when_children_clamp_at_ceiling(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """group_volume should equal the commanded target even when children clamp at 100."""
        leader = register_player("leader", "Leader", volume=90)
        child1 = register_player("child1", "Child 1", volume=90)
        child2 = register_player("child2", "Child 2", volume=10)

        leader._attr_group_members = ["leader", "child1", "child2"]
        # Call update_state twice so group_volume reflects the real average
        # (first call sets group_members in the state; second call reads
        # children's volumes through the now-populated group_members)
        leader.update_state(signal_event=False)
        leader.update_state(signal_event=False)

        # Initial calculated group volume based on child player volumes
        assert leader.state.group_volume == 63

        for p in [leader, child1, child2]:
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        await controller.set_group_volume(leader, 100)

        # Current (broken) behavior:
        # Delta = 100 - 63 = 37
        # leader: 90+37=127 → clamped to 100
        # child1: 90+37=127 → clamped to 100
        # child2: 10+37=47

        # The derived average is (100+100+47)/3 = 82, not 100.
        # The UI should show 100 (the user's intent), not the clamped average.
        pytest.xfail("recomputed group_volume should always match the commanded group_volume")
        assert leader.state.group_volume == 100  # type: ignore[unreachable]

        # Additionally, the child volume levels should have been set to values
        # that would have caused the group volume, if recalculated, to be the same
        # as the commanded value! Otherwise, a slight future change to a child volume
        # would cause the group volume to jump far more substantially than it should
        # on the next recalculation.
        # The below assertions assume the correct behavior would redistribute the
        # excess delta so the average genuinely equals the commanded value.
        assert leader.state.volume_level == 100
        assert child1.state.volume_level == 100
        assert child2.state.volume_level == 100

    async def test_group_volume_matches_target_when_children_clamp_at_floor(
        self,
        controller: PlayerController,
        register_player: RegisterPlayer,
    ) -> None:
        """group_volume should equal the commanded target even when children clamp at 0."""
        leader = register_player("leader", "Leader", volume=10)
        child1 = register_player("child1", "Child 1", volume=10)
        child2 = register_player("child2", "Child 2", volume=90)

        leader._attr_group_members = ["leader", "child1", "child2"]
        leader.update_state(signal_event=False)
        leader.update_state(signal_event=False)

        assert leader.state.group_volume == 36

        for p in [leader, child1, child2]:
            p.volume_set = AsyncMock()  # type: ignore[method-assign]

        await controller.set_group_volume(leader, 0)

        # Current (broken) behavior:
        # Delta = 0 - 36 = -36
        # leader: 10-36=-26 → clamped to 0
        # child1: 10-36=-26 → clamped to 0
        # child2: 90-36=54
        # Derived average = (0+0+54)/3 = 18, not 0.
        #
        # The UI should show 0 (the user's intent), not the clamped average.
        pytest.xfail("recomputed group_volume should always match the commanded group_volume")
        assert leader.state.group_volume == 0  # type: ignore[unreachable]

        # All children should be at 0 — the excess delta on child2 should be
        # redistributed so the average genuinely equals the commanded value.
        assert leader.state.volume_level == 0
        assert child1.state.volume_level == 0
        assert child2.state.volume_level == 0

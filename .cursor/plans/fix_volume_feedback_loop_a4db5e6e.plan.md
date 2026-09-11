---
name: fix volume feedback loop
overview: Fix the plugin volume feedback loop that occurs when Spotify Connect drives a sync group, using a reactive approach that moves plugin volume notifications into the state system and eliminates per-child callbacks entirely.
todos:
  - id: branch
    content: Create new branch from origin/dev (e.g. fix/plugin-volume-feedback-loop-v2)
    status: completed
  - id: player-model
    content: Add volume_set_optimistic() method to Player base class in models/player.py
    status: completed
  - id: controller-optimistic
    content: "In _handle_cmd_volume_set: use volume_set_optimistic() for native volume and remove the inline plugin callback"
    status: completed
  - id: controller-group
    content: "In set_group_volume: force group_player.update_state() after asyncio.gather"
    status: completed
  - id: controller-hook
    content: "In signal_player_state_update: add reactive hook that fires debounced plugin on_volume when group_volume changes"
    status: completed
  - id: spotify-inbound
    content: "In Spotify Connect volume_changed handler: route through cmd_group_volume when target is a group player"
    status: completed
  - id: tests
    content: "Write focused test suite: reactive callback, group volume coherence, standalone player, inbound routing, echo suppression"
    status: completed
  - id: precommit
    content: Run pre-commit hooks and verify all tests pass
    status: completed
isProject: false
---

# Fix Plugin Volume Feedback Loop (Clean Rewrite)

## The Bug

When Spotify Connect is the active plugin source on a group player (sync group or ad-hoc sync), adjusting volume causes a feedback loop:

1. `set_group_volume` dispatches `_handle_cmd_volume_set` to each child
2. Each child's `_handle_cmd_volume_set` finds the plugin source (because `__final_active_source` inherits the group's active source) and calls `plugin_source.on_volume(child_volume)`
3. This sends N Spotify Web API calls (one per child, each with a *different* volume)
4. Spotify echoes each back as `volume_changed`, routed to `cmd_volume_set(group_player_id, vol)`
5. For GROUP players, this redirects to `cmd_group_volume` -> `set_group_volume` -> dispatches to all children again
6. Infinite loop with oscillating volumes

## Root Cause

Two problems combine to create the feedback loop:

1. **Per-child plugin callbacks**: `_handle_cmd_volume_set` unconditionally fires the plugin `on_volume` callback for **any** player whose `active_source` matches a plugin -- including group children that merely inherit the active source from their parent. During a group volume operation, this fires N callbacks (one per child, each with a different individual volume) instead of a single callback with the group volume.

2. **Stale group volume state**: When `set_group_volume` dispatches volume commands to children, provider implementations that rely on async hardware confirmation (Chromecast, Sonos, HEOS, etc.) don't update `_attr_volume_level` until the hardware reports back. The `group_volume` computed property -- an average of children's `state.volume_level` -- remains stale until those async callbacks arrive. If a Spotify echo arrives and routes through `cmd_group_volume` before hardware confirms, `set_group_volume` computes a non-zero delta from the stale average, re-dispatching unnecessary child volume changes.

## Design: Reactive Plugin Volume Notifications

Rather than trying to fix the inline plugin callback in `_handle_cmd_volume_set` (which requires a `from_group_volume` flag, careful restructuring to compute group averages, and duplicated callback logic in both `_handle_cmd_volume_set` and `set_group_volume`), we adopt a **reactive approach**:

**Remove the plugin `on_volume` callback from `_handle_cmd_volume_set` entirely.** Instead, add a hook in `signal_player_state_update` that fires the plugin callback whenever `group_volume` changes on a player that **owns** a plugin source (checked via `plugin_source.in_use_by == player.player_id`).

This works because:

- **`group_volume` is already computed for every player** as part of state recalculation. For non-group players, it equals their individual `volume_level`. For groups/sync leaders, it's the average of powered children.
- **The `in_use_by` check** ensures only the plugin-owning player fires the callback -- not children that merely inherit the active source. This eliminates per-child callbacks without needing a flag.
- **The callback always sends the real computed `group_volume`**, not an individual child volume or a target that might differ from the actual average after clamping.
- **Natural debouncing**: The hook uses `call_later` with a `task_id` (0.25s debounce). For individual child volume changes, this stacks with the existing 0.25s `trigger_player_update` debounce on the group player, giving ~0.5s total latency -- acceptable for an async informational update to the Spotify app. For group slider drags, the forced `group_player.update_state()` in `set_group_volume` fires the hook immediately, then the 0.25s debounce rate-limits the Spotify API calls.
- **Edge cases handled automatically**: membership changes, power state changes, or any other event that shifts the group average will trigger the plugin callback without special-case code.

## Why We Need Optimistic Volume Updates

Currently, the controller handles native vs fake volume asymmetrically:

- **Fake volume**: The controller optimistically sets `extra_data[ATTR_FAKE_VOLUME]` and calls `update_state()` synchronously. The player's state immediately reflects the new value.
- **Native volume**: The controller calls `player.volume_set()` and returns. Whether the internal state updates depends entirely on the provider implementation -- roughly half of providers (AirPlay, Bluesound, Alexa, Fully Kiosk, Dashie Kiosk) do their own optimistic update inside `volume_set()`, while the other half (Chromecast, Sonos, HEOS, Squeezelite, DLNA, etc.) don't update until hardware confirms asynchronously.

This inconsistency means that after `set_group_volume` dispatches to all children via `asyncio.gather`, `group_volume` may still reflect the **old** child volumes for providers that wait for hardware confirmation. If a Spotify echo arrives and routes through `cmd_group_volume` during this window, `set_group_volume` computes a non-zero delta from the stale average, re-dispatching unnecessary child volume changes.

The fix adds `volume_set_optimistic()` to the `Player` base class. It wraps the provider's `volume_set()` and then sets `_attr_volume_level` + calls `update_state()`, guaranteeing that internal state is coherent immediately after the hardware command succeeds. For providers that already do optimistic updates internally, the base class's `update_state()` detects no change and returns early -- a harmless no-op.

This keeps `_attr_volume_level` mutation inside the `Player` class (the controller never directly sets `_attr_*` attributes -- an established convention in this codebase) while giving the controller a clean public API.

## The Fix -- Four Targeted Changes

### Change 1: `volume_set_optimistic()` on the Player base class

In [`models/player.py`](music_assistant/models/player.py), add a new method near the existing `volume_set()` definition (~line 369):

```python
async def volume_set_optimistic(self, volume_level: int) -> None:
    """
    Set volume and optimistically update internal state.

    Calls the provider's volume_set(), then unconditionally updates
    _attr_volume_level and triggers a state recalculation. This ensures
    that computed properties like group_volume reflect the new value
    immediately, rather than waiting for async hardware confirmation.

    For providers that already update state inside volume_set(), the
    subsequent update_state() call here detects no change and is a no-op.

    :param volume_level: volume level (0..100) to set on the player.
    """
    await self.volume_set(volume_level)
    self._attr_volume_level = volume_level
    self.update_state()
```

### Change 2: Optimistic volume + remove inline plugin callback in `_handle_cmd_volume_set`

In [`controller.py` ~line 2883](music_assistant/controllers/players/controller.py):

1. **Remove** the existing plugin callback block (lines 2915-2918):
```python
# REMOVE THIS:
if plugin_source := self._get_active_plugin_source(player):
    if plugin_source.on_volume:
        await plugin_source.on_volume(volume_level)
```

2. **Replace** `player.volume_set(volume_level)` with `player.volume_set_optimistic(volume_level)` for the native volume path, with a comment:
```python
    if player.volume_control == PLAYER_CONTROL_NATIVE:
        # Use optimistic volume to guarantee that the player's internal
        # state (and therefore computed properties like group_volume)
        # reflects the commanded volume immediately after the hardware
        # call succeeds, rather than waiting for async hardware
        # confirmation. This is critical for group volume coherence:
        # without it, providers like Chromecast/Sonos/HEOS leave
        # group_volume stale, and inbound plugin echoes that route
        # through cmd_group_volume compute a non-zero delta from the
        # stale average, re-dispatching unnecessary child changes.
        #
        # Plugin volume notification is handled reactively by
        # signal_player_state_update when group_volume changes --
        # not here. This ensures the plugin always receives the
        # correct group average (not an individual child volume)
        # and naturally debounces rapid volume changes.
        await player.volume_set_optimistic(volume_level)
        return
```

### Change 3: Forced group state coherence in `set_group_volume`

In [`controller.py` ~line 1739](music_assistant/controllers/players/controller.py), force the group player's state to recalculate after all children are set:

```python
async def set_group_volume(self, group_player: Player, volume_level: int) -> None:
    ...
    await asyncio.gather(*coros)

    # Force the group player's state to recalculate immediately so that
    # group_volume reflects the children's new volumes. Without this,
    # the group state update is debounced by 0.25s -- if a plugin echo
    # arrives in that window, set_group_volume would read a stale
    # group_volume and compute a non-zero delta. This also triggers
    # the reactive plugin volume hook in signal_player_state_update,
    # which debounces the actual plugin callback by another 0.25s to
    # rate-limit outbound API calls during rapid slider drags.
    group_player.update_state()
```

No inline plugin callback needed -- the reactive hook in `signal_player_state_update` handles it.

### Change 4: Reactive plugin volume hook in `signal_player_state_update`

In [`controller.py` ~line 1597](music_assistant/controllers/players/controller.py), add a hook that fires a debounced plugin callback when `group_volume` changes on a player that owns a plugin source:

```python
    # signal player update on the eventbus
    if player.state.type != PlayerType.PROTOCOL:
        self.mass.signal_event(EventType.PLAYER_UPDATED, object_id=player_id, data=player)

    # Reactive plugin volume notification: when group_volume changes,
    # notify any plugin source owned by this player. This replaces the
    # previous inline callback in _handle_cmd_volume_set, which fired
    # per-child during group operations (causing feedback loops) and
    # sent individual child volumes instead of the group average.
    # The debounced call_later naturally rate-limits outbound API calls.
    if "group_volume" in changed_values:
        for plugin_source in self.get_plugin_sources():
            if plugin_source.in_use_by == player.player_id and plugin_source.on_volume:
                self.mass.call_later(
                    0.25,
                    plugin_source.on_volume,
                    player.state.group_volume,
                    task_id=f"plugin_volume_{player.player_id}",
                )
```

### Change 5: Inbound Spotify volume routing

In [`spotify_connect/__init__.py` ~line 847](music_assistant/providers/spotify_connect/__init__.py), route inbound `volume_changed` through `cmd_group_volume` when the target is a group player:

```python
if self._source_details.in_use_by:
    volume = int(int(volume) / 65535 * 100)
    self._last_volume_sent_to_spotify = volume
    player = self.mass.players.get_player(self._source_details.in_use_by)
    if player and (player.state.type == PlayerType.GROUP or player.state.group_members):
        await self.mass.players.cmd_group_volume(self._source_details.in_use_by, volume)
    else:
        await self.mass.players.cmd_volume_set(self._source_details.in_use_by, volume)
```

This ensures inbound Spotify volume changes propagate to all group children proportionally (via the additive-delta algorithm), rather than only affecting the individual target player. Without this, ad-hoc sync leaders (PLAYER type with `group_members`) would have only their own volume set, shifting the group average asymmetrically.

### Why This Breaks the Loop

After these changes:

1. User drags group slider to 60 -> `set_group_volume` -> children set optimistically -> `group_player.update_state()` forced -> `group_volume` = 60 -> reactive hook schedules debounced `on_volume(60)` -> Spotify receives 60
2. Spotify echoes `volume_changed(60)` -> `cmd_group_volume(group_id, 60)` (via Change 5) -> `set_group_volume`
3. `set_group_volume` reads `group_volume` = 60 (coherent due to optimistic updates) -> delta = 0 -> children dispatched with unchanged volumes -> `group_player.update_state()` sees no change -> hook does not fire
4. Even if hook did fire (rounding edge case): `on_volume(60)` -> Spotify Connect's `_last_volume_sent_to_spotify == 60` check -> **suppressed**
5. Loop broken at multiple levels

Individual child volume changes also work correctly:
1. User changes child volume -> `_handle_cmd_volume_set` sets child optimistically (no plugin callback here)
2. Child's `update_state()` triggers debounced group `update_state()` (0.25s)
3. Group's `group_volume` changes -> reactive hook fires debounced `on_volume(new_average)` (+0.25s)
4. Spotify receives the correct **group average**, not the individual child volume (~0.5s total latency, acceptable for async informational update)

## What We Are NOT Doing (vs the closed PR)

The closed PR (#3512 final state) included these additional changes that we will **omit**:

- **`from_group_volume` flag on `_handle_cmd_volume_set`** -- not needed; the reactive hook eliminates per-child callbacks without requiring call-site context flags
- **`_handle_volume_plugin_callback` helper** (~120 lines) with multi-group resolution, projected group average computation, sync leader self-recognition -- replaced by a 6-line reactive hook
- **`cmd_group_volume` coalescing loop** with `_group_vol_in_flight` / `_group_vol_target` dicts -- not needed; debounced hook naturally rate-limits
- **Fresh average computation in `set_group_volume`** (replacing `group_player.state.group_volume`) -- solved by optimistic state updates that keep the cached average coherent
- **Boundary redistribution** in `set_group_volume` -- not needed for the feedback loop fix
- **Outbound volume debounce** (`_VOLUME_API_DEBOUNCE`, `_send_volume_to_spotify`) -- replaced by the hook's `call_later` debounce
- **Time-windowed echo suppression** (`_VOLUME_ECHO_SUPPRESS_WINDOW`, `_last_volume_change_received_time`) -- the value-match dedup is sufficient once per-child callbacks are eliminated and the delta is zero
- **Extensive `[GroupVolume]` debug logging** -- per maintainer feedback, either drop or use verbose log level
- **1336-line test file with 41 test cases** -- replaced by a focused test suite (~6-8 tests)

## Files Changed

- [`music_assistant/models/player.py`](music_assistant/models/player.py) -- `volume_set_optimistic()` method (~15 lines added)
- [`music_assistant/controllers/players/controller.py`](music_assistant/controllers/players/controller.py) -- remove inline plugin callback + optimistic volume + forced group state recalc + reactive hook (~20 net lines changed)
- [`music_assistant/providers/spotify_connect/__init__.py`](music_assistant/providers/spotify_connect/__init__.py) -- inbound volume routing (~10 lines changed)
- `tests/core/test_plugin_volume_isolation.py` -- focused test suite

## Documentation Updates

After implementing the code changes, update the architecture docs to reflect the new behavior. Sections that become inaccurate:

### [`docs/architecture/07-volume.md`](docs/architecture/07-volume.md) (4 sections)
- **"Individual Volume Routing"** flowchart: Remove the inline plugin `on_volume` step from the Mermaid diagram. Note that plugin notification is now reactive (handled by `signal_player_state_update`).
- **"Plugin Volume Callbacks"** (~line 50): Rewrite to describe the reactive hook model. The code block showing inline `on_volume` inside `_handle_cmd_volume_set` must be removed. Explain the `in_use_by` check, debounced `call_later`, and that the callback always sends the computed `group_volume`.
- **"Group Volume — The Additive-Delta Algorithm"** (~line 68): Add the forced `group_player.update_state()` after `asyncio.gather` and explain why (state coherence for delta computation on subsequent calls).
- **"Volume Command Flow Summary"** diagram (~line 217): Remove the `PC[Plugin on_volume callback]` node from inline flow. Add note about reactive notification.

### [`docs/architecture/04-player-controller.md`](docs/architecture/04-player-controller.md) (2 sections)
- **"Volume Routing"** (~line 162): Remove step 3 ("Active plugin — calls `plugin.on_volume()` if present") from the `_handle_cmd_volume_set` description. Note that native volume now uses `volume_set_optimistic()`.
- **"Event Signaling"** (~line 242): Add the new reactive plugin volume hook to the list of `signal_player_state_update` side effects: debounced `on_volume` callback when `group_volume` changes on a player that owns a plugin source.

### [`docs/architecture/11-plugin-system.md`](docs/architecture/11-plugin-system.md) (2 sections)
- **"Callback Fields"** table (~line 46): Change the `on_volume` "Invoked by" column from `_handle_cmd_volume_set` to `signal_player_state_update` (reactive hook on `group_volume` change).
- **"`in_use_by` Semantics"** (~line 178): Update to reflect that the reactive hook solves the group member gap — individual member volume changes now propagate to the plugin via the group's `group_volume` recalculation. Remove the "feedback loop problem" framing.

### [`docs/architecture/03-player-model.md`](docs/architecture/03-player-model.md) (1 section)
- **"Player Control Commands"** table (~line 202): Add `volume_set_optimistic()` as a new method on the Player base class, noting it wraps `volume_set()` with an optimistic state update.

## Branch Strategy

Create a new clean branch from `origin/dev`. The old `fix/plugin-volume-feedback-loop` branch carries the over-engineered commit; we start fresh.

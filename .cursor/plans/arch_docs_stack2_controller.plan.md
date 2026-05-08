---
name: arch_docs_stack2_controller
overview: "Refresh docs/architecture/04-player-controller.md to document the new player-controller helpers added upstream since the docs were originally written: the player-state pub/sub (subscribe_player_state_update / _dispatch_state_update_subscribers / _forward_state_update), the wait_for_player_update / _wait_for_playback_state synchronization helpers, the get_player_lock re-entrant per-purpose locking primitive, and the deselect_source first-class command. Also fix one order-of-operations error in docs/architecture/07-volume.md: upstream's _handle_cmd_volume_set fires the plugin on_volume callback BEFORE the native/fake/delegate routing branches, not after."
todos:
  - id: branch
    content: Cut docs/architecture-controller-update from docs/architecture-models-update (Stack 1's branch)
    status: pending
  - id: edit_controller_doc
    content: Update docs/architecture/04-player-controller.md — add State Update Fan-Out, Synchronization Helpers, Per-Player Locking, deselect_source sections
    status: pending
  - id: fix_volume_order
    content: Update docs/architecture/07-volume.md — correct order-of-operations diagram and prose so plugin on_volume fires before routing branches
    status: pending
  - id: verify
    content: pre-commit + cross-check against upstream code
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture-models-update
    status: pending
isProject: false
---

# Stack 2 — Player controller refresh + volume order-of-ops fix

## Branch

Cut from Stack 1's branch (`docs/architecture-models-update`):

```bash
git fetch origin
git checkout docs/architecture-models-update
git pull --ff-only origin docs/architecture-models-update
git checkout -b docs/architecture-controller-update
```

## Edits — `docs/architecture/04-player-controller.md`

### Add a new section: "State Update Fan-Out"

Insert under the existing "Event Signaling" section (around the existing `signal_player_state_update` discussion).

Reference: `_forward_state_update` in [music_assistant/controllers/players/controller.py](music_assistant/controllers/players/controller.py) lines 1801–1825. Bodies of `subscribe_player_state_update` (line 2070), `_dispatch_state_update_subscribers` (line 2091).

Suggested wording:

> ### State Update Fan-Out
>
> Beyond emitting events on the bus, every player state update is fanned out by the controller through three complementary mechanisms:
>
> 1. **Hook propagation to related players** (`_forward_state_update`): when a player updates, the controller calls the appropriate hook (`on_group_updated`, `on_sync_parent_updated`, `on_group_member_updated`, `on_protocol_parent_updated`) on every related player. See [03-player-model.md](03-player-model.md#update-notification-hooks).
> 2. **Internal subscribers** (`subscribe_player_state_update` / `_dispatch_state_update_subscribers`): callers can register a synchronous callback receiving `(Player, changed_values)` where `changed_values` maps attribute name to a `(previous, new)` tuple. Returns an unsubscribe function. Used by long-running commands that need to know exactly when a state attribute flips.
> 3. **Async wait helpers** (`wait_for_player_update`, `_wait_for_playback_state`): `wait_for_player_update(player_id, attribute_name=..., attribute_value=..., timeout=...)` is an `asynccontextmanager` that subscribes on entry, runs the body (which typically triggers the awaited update), then waits for the matching update on exit. Skips the wait if the value already matches at entry. `_wait_for_playback_state` builds on it for the common "wait until PLAYING/IDLE" case.

### Add a new section: "Per-Player Locking"

Insert under the existing power/playback locking discussion.

Reference: `get_player_lock` in [music_assistant/controllers/players/controller.py](music_assistant/controllers/players/controller.py) lines 168–203.

Suggested wording:

> ### Per-Player Locking
>
> Player commands that must not race (power, playback, volume) acquire a lock via `get_player_lock(player_id, purpose=PlayerLockPurpose.PLAYBACK)`. The lock is **purpose-scoped** — commands with different purposes can run concurrently on the same player (e.g. a volume change and a power change), but two commands with the same purpose serialize.
>
> The lock is **re-entrant per asyncio Task**: nested calls within the same task skip re-acquisition (preventing self-deadlock), but deferred callbacks (`call_later`, `create_task`) run in a fresh task and acquire the lock fresh. The implementation tracks ownership in `self._task_held_locks: dict[int, set[str]]` keyed by task ID.
>
> Locks are also cleaned up at unregister time (along with throttlers and protocol evaluations) to prevent leakage when players disappear (#3554).

### Add a row for `deselect_source`

Find the player-commands table or list. Add:

> `deselect_source(player_id)` — Stop the player and clear its current source. Used when an external source (plugin/receiver) disconnects and the player should stop rather than fall through to another source. Source: [music_assistant/controllers/players/controller.py](music_assistant/controllers/players/controller.py) line 1102.

## Edit — `docs/architecture/07-volume.md` (order-of-operations fix)

The current routing diagram and prose claim the plugin `on_volume` callback fires AFTER the native/fake/delegate routing. **This is wrong** — upstream's `_handle_cmd_volume_set` in [music_assistant/controllers/players/controller.py](music_assistant/controllers/players/controller.py) lines 3275–3283 fires the callback BEFORE:

```python
# Upstream order:
# 1. Clamp + GROUP redirect + auto-unmute + scale_volume_to_device
# 2. await plugin_source.on_volume(volume_level)   <-- HERE
# 3. if NATIVE: await player.volume_set(device_volume)
#    elif FAKE: extra_data[ATTR_FAKE_VOLUME] = ...
#    elif NONE: raise
#    elif PlayerControl: ...
#    elif protocol_player: recurse
```

Required edits in [docs/architecture/07-volume.md](docs/architecture/07-volume.md):

1. **Routing diagram (mermaid block near top of file):** swap the order so the "Active plugin source owned by this player?" check fires BEFORE the `volume_control type?` decision, not after the routing branches. The post-routing `K -> O`, `L -> O`, `O -> P` edges should become pre-routing `H -> O`, `O -- Yes --> P -> J`, `O -- No --> J`.
2. **Inline lead-in paragraph (currently states "After `_handle_cmd_volume_set` finishes its native/fake/delegate routing..."):** rewrite to "Before `_handle_cmd_volume_set` dispatches to the native/fake/delegate routing, if the player is the direct owner of an active plugin source (`plugin_source.in_use_by == player.player_id`), it `await`s `on_volume(volume_level)` synchronously. This guarantees the plugin sees the commanded value before any hardware confirmation can echo back."
3. **"Plugin Volume Callbacks" section:** rewrite the `_handle_cmd_volume_set` step to "after the auto-unmute check + `scale_volume_to_device`, **before** the volume_control routing branches".
4. **"Volume Command Flow Summary" mermaid (lower in file):** the `HV --> VR -> PV3` chain should become `HV --> PV3 -> VR`.

This is a doc accuracy fix — upstream's behavior was always the same, our prior rewrite simply transcribed the wrong order. No upstream code change is needed.

## Verification

```bash
pre-commit run --files docs/architecture/04-player-controller.md docs/architecture/07-volume.md

# Cross-check the volume order claim:
git show upstream/dev:music_assistant/controllers/players/controller.py | sed -n '3270,3295p'
# Confirm: plugin_source.on_volume await comes BEFORE the volume_control if-chain.
```

## Commit + PR

Single commit message:

```
docs(architecture): document state-update fan-out, locking, deselect_source; fix volume order

Adds documentation of the player controller's state update fan-out
(subscribe_player_state_update, wait_for_player_update,
_wait_for_playback_state), per-player re-entrant locking
(get_player_lock), and the deselect_source command.

Also corrects an order-of-operations error introduced in the recent
volume rewrite: upstream fires the plugin on_volume callback BEFORE
the native/fake/delegate routing branches, not after.
```

PR base: `docs/architecture-models-update`.

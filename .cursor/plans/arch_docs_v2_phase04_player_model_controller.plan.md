---
name: arch_docs_v2_phase04_player_model_controller
overview: "Phase 4. Refresh 03-player-model.md and 04-player-controller.md: the update_state() pipeline now uses selective cache invalidation and input snapshots, the per-player throttler was removed, command locking is PlayerLockPurpose-keyed with a timeout escape, play_media can release captured players from their group, plugin volume routing goes through AudioSource, and sleep timers and setup flows are new player surfaces."
todos:
  - id: preflight
    content: "Pre-flight: verify the Player attribute/method surface, update_state pipeline, lock semantics, and command surface against the working tree"
    status: pending
  - id: model_update_state
    content: "03-player-model.md: rewrite the update_state() pipeline and caching sections (selective invalidation, input snapshot, state fingerprint, mark_state_dirty)"
    status: pending
  - id: model_attrs
    content: "03-player-model.md: refresh the attribute and method tables; add sleep timer, palette, setup-flow surface, position anchor reconciliation"
    status: pending
  - id: model_controls
    content: "03-player-model.md: document PLAYER_CONTROL_PROTOCOL/follow_protocol, POWER degradation to NONE, and the group_volume exclude_self nuance"
    status: pending
  - id: model_protocols
    content: "03-player-model.md: add derived_from to output_protocols and the native-protocol-endpoint case"
    status: pending
  - id: ctrl_registration
    content: "04-player-controller.md: fix the registration flow (throttler removed, CONF_REPORTED_MAC, group players do not restore fake power)"
    status: pending
  - id: ctrl_locking
    content: "04-player-controller.md: fix the command decorator and concurrency table (PlayerLockPurpose keys, no throttling, 30s lock timeout); remove the duplicated locking section"
    status: pending
  - id: ctrl_commands
    content: "04-player-controller.md: refresh the command surface (sleep timer API, scopes, play_media group override, cmd_set_members/cmd_power locking, AudioSource pause)"
    status: pending
  - id: ctrl_volume_fanout
    content: "04-player-controller.md: fix volume routing for AudioSource plugin notification and device_volume redirect; add external power-off unsync to the fan-out section"
    status: pending
  - id: verify
    content: "pre-commit, confirm the diff touches only docs, commit and push"
    status: pending
isProject: false
---

# Phase 4 — Player model and player controller

Files: `docs/architecture/03-player-model.md`, `docs/architecture/04-player-controller.md`.

These are the most carefully written docs in the tree, so precision matters more than coverage.
Verify every claim below before writing. Line-count references in both docs are stale
(`player.py` ~2142 → ~3051; controller ~3242 → ~4215) — re-measure at edit time.

Related in-tree README: `music_assistant/controllers/players/README.md`. Complement it; link for
module inventory.

## `03-player-model.md`

### The `update_state()` pipeline and caching

The doc describes an unconditional `self._cache.clear()` on every update and a 9-step pipeline
with explicit noise filtering of diff keys. Current behavior:

- **Selective invalidation** — config-derived properties in `_CONFIG_CACHED_PROPS` survive.
- **Input snapshot** — `__collect_input_snapshot()` gives a cheap early exit when a player's own
  inputs are unchanged.
- **State fingerprint** — computed internally, excluding `seq_no` and `last_poll`.
- **`mark_state_dirty()`** — how cross-player derived changes are propagated.
- `signal_player_state_update` now also carries `media_position_jumped` (and `skip_forward`).
- Add **position anchor reconciliation**: `_reconcile_position_anchor`,
  `on_player_position_jumped`, and `MEDIA_IDENTITY_KEYS` (which now includes `palette`).

Driving PR: #4579 ("Make player state change detection exact and cheap").

Note but do not overstate: `_forward_state_update` carries an upstream TODO about making fan-out
change-aware. Mention it as a known limitation, not as documented behavior.

### Attributes and methods

Missing from the tables: `sleep_timer_expires_at`; expanded `needs_setup` semantics (setup flows);
`derived_from` on `OutputProtocol`; async `palette` on current media. Missing methods and
properties: `mark_state_dirty()`, `trigger_player_update()`, `set_sleep_timer_expires_at()`,
`corrected_elapsed_time`, `available_for_playback`, and the setup-flow surface
(`can_run_setup_flow`, `run_setup_flow`, `setup_data`, `setup_required_reason`).

### Control resolution

- Document `PLAYER_CONTROL_PROTOCOL` / `"follow_protocol"` (`music_assistant/constants.py`) — the
  explicit auto-select sentinel for volume and mute control. The doc omits it entirely.
- `power_control` degrades a configured `NATIVE` to `NONE` when `PlayerFeature.POWER` is no longer
  advertised. Sync groups are the main case, which ties into Phase 5.
- `group_volume` / `group_volume_muted`: `iter_group_members` is called with
  `exclude_self=self.type != PlayerType.PLAYER`, so for `PlayerType.PLAYER` sync leaders the
  leader **is** included in the max/mute aggregation. The doc omits this.
- `__final_active_group`: the doc implies active groups are those playing or paused. Sync groups
  are now tested via `SyncGroupPlayer.is_active_session` (sync leader set, idle grace pending, or
  reform debounce pending) using raw `powered`, not playback state. Keep this short here and
  cross-link Phase 5, which owns the session lifecycle.

### Output protocols

Add `derived_from` on each `OutputProtocol` entry (#4609), and the case where a player is itself a
native protocol endpoint (`provider.domain in PROTOCOL_PRIORITY` and `SET_MEMBERS`) and appears in
its own `output_protocols` with `is_native=True`.

The control-priority table and playback `PROTOCOL_PRIORITY` were verified as still accurate — do
not churn them.

## `04-player-controller.md`

### Registration

- Remove step 3, "Throttler setup — `Throttler(1, 0.05)`". The per-player throttler was deleted in
  #4024 ("Drop redundant per-player throttler and harden the command lock").
- Add: `CONF_REPORTED_MAC` is persisted to config, not only to `extra_data`.
- Add: group players deliberately do **not** restore fake power on restart.

### Locking and concurrency

- `@handle_player_command(lock=True)` no longer keys locks on `f"{fn.__name__}_{player_id}"`. It
  uses `PlayerLockPurpose` keys via `get_player_lock` (`playback_{id}`, `volume_{id}`).
- Delete the "Throttling — runs inside `_player_throttlers`" step and the `_player_throttlers` row
  from the Concurrency Controls table.
- Add the **lock timeout escape**: `get_player_lock` logs at 5s, waits 25s more, then proceeds
  **without** the lock rather than deadlocking.
- There is a **duplicated "Per-Player Locking" section** (roughly lines 227–241 repeating
  229–239). Collapse it.

### Command surface

- Add the sleep timer API: `players/sleep_timer/get`, `players/sleep_timer/set`,
  `players/sleep_timer/clear`.
- Every player `@api_command` now declares `required_scope=Scope.PLAYERS_READ` or
  `Scope.PLAYERS_CONTROL` (#4613). Mention it and cross-link `19-authentication.md` (Phase 14)
  rather than explaining the scope model here.
- **`play_media` behavior changed materially.** The doc only describes redirect-to-leader via
  `_get_player_with_redirect`. There is now `CONF_PLAY_MEDIA_OVERRIDES_GROUP` (default `True`),
  which releases a captured player via `_release_player_for_play_media` — ungrouping, removing it
  from a dynamic group, or stopping/powering off a static group — before playing standalone.
- `cmd_set_members` is not wrapped in `@handle_player_command(lock=…)`; it acquires
  `get_player_lock(parent, PlayerLockPurpose.PLAYBACK)` internally.
- `cmd_power` is explicitly serialized with `PlayerLockPurpose.PLAYBACK` because it forms and
  dissolves groups.
- `_handle_cmd_pause` now pauses an active `AudioSource` via `on_source_control(PAUSE)` where
  possible instead of always falling through to stop (#4401).

### Volume routing and state fan-out

- The plugin notification path is wrong. The doc says `plugin_source.on_volume(volume_level)`
  gated on `plugin_source.in_use_by == player.player_id`. It is now
  `_get_active_audio_source()` → `plugin_prov.on_volume_change(audio_source.item_id, volume_level)`,
  gated on `active_queue.queue_id == player.player_id` (#3938). Phase 12 owns the AudioSource model
  itself; here just make the routing correct and cross-link.
- Protocol volume redirect forwards `device_volume` (already scaled), not logical 0–100 (#4461).
- Add to the fan-out section: an external power-off now unsyncs the player via `cmd_ungroup` in
  `_handle_membership_cleanup_on_state_change` (#4463).

The #3659 power-management note (power_control does not delegate to protocol player IDs) was
verified as still accurate.

## Verification

- `rg "PlayerLockPurpose|_release_player_for_play_media|CONF_PLAY_MEDIA_OVERRIDES_GROUP|_collect_input_snapshot|_CONFIG_CACHED_PROPS|sleep_timer"`.
- Confirm `_player_throttlers` is really gone: `rg "_player_throttlers|Throttler\(1, 0.05\)"`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): refresh player model and controller for state, locking and command changes

Phase 4 of the upstream/dev refresh.
```

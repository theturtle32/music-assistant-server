# Sub-plan 3: Grouping and Volume

**Scope**: The three grouping models (sync groups, universal groups, ad-hoc sync), group volume control, and plugin volume callbacks. This is the area where our prior PRs had the most misunderstandings — extra care is needed.

**Context**: Sub-plans 1 and 2 are complete. Seven architecture docs exist under `docs/architecture/`: `00-overview.md` through `05-protocol-linking.md` plus `15-provider-lifecycle.md`. This sub-plan builds on all of them and reconciles at the end.

**Model**: 1M context recommended. This phase has the highest cross-cutting complexity — grouping touches the player model, player controller, sync_group provider, universal_group provider, protocol linking, and volume control simultaneously. Reconciliation must read all 7 prior documents.

## Deliverables

You will produce 2 markdown files under `docs/architecture/`.

### 1. `docs/architecture/06-grouping.md` — Grouping Architecture

The three grouping models, membership, formation/dissolution lifecycle, and the relationships between `group_members`, `synced_to`, and `active_group`.

**Must cover:**

- **The three grouping models** — when each applies, how they differ architecturally:

  **a. Sync Group** (`music_assistant/providers/sync_group/`):
  - Persistent group entity (`SyncGroupPlayer`, `PlayerType.GROUP`) with its own queue
  - Created/removed via `SyncGroupProvider.create_group_player()` / `remove_group_player()`
  - Player ID format: `syncgroup_{random_8_chars}`
  - **Sync leader concept**: The sync group doesn't play audio directly — it delegates to a selected sync leader from its members. The leader receives `play_media`, syncs other members to itself.
  - **Leader selection**: current leader if available, then prioritize static members, then first available member
  - **Static vs dynamic groups**: Static has fixed membership defined at creation (`CONF_GROUP_MEMBERS`). Dynamic supports runtime `SET_MEMBERS`. Controlled by `CONF_DYNAMIC_GROUP_MEMBERS`.
  - **Protocol compatibility**: Only same-protocol players can be grouped. Enforced via `can_group_with` from the first member added.
  - **Feature inheritance**: Base feature is `PLAY_MEDIA`. When a sync leader is active, additional features are inherited (`ENQUEUE`, `GAPLESS_PLAYBACK`, `VOLUME_SET`, `VOLUME_MUTE`, `MULTI_DEVICE_DSP`).
  - **State delegation**: Playback state, elapsed time from sync leader. Current media stored on group itself. Group members from sync leader's reported members or internal list.
  - **Formation/dissolution lifecycle**: `_form_syncgroup()` on play (cancel dissolve timer, ensure static members, select leader, sync members). `_dissolve_syncgroup()` on stop (5-second delay to prevent churn during track changes). Trace through the code to document the full flow.
  - The existing `sync_group/README.md` is thorough — verify every claim against the code, incorporate accurate content, add anything it misses.

  **b. Universal Group** (`music_assistant/providers/universal_group/`):
  - Persistent group entity (`UniversalGroupPlayer`, `PlayerType.GROUP`) — similar to sync group but for **cross-protocol** grouping
  - Player ID format: `ugp_{random_8_chars}`
  - **Server-side mixing**: Unlike sync groups that delegate to a vendor's native sync protocol, universal groups use `UGPStream` — MA server reads the audio source, multicasts it to each member as an independent HTTP stream (one per member)
  - **Always requires flow mode**: `requires_flow_mode = True`
  - **Base features**: `PLAY_MEDIA`, `POWER`, `VOLUME_SET`, `MULTI_DEVICE_DSP`
  - **Dynamic HTTP routes**: Registers `/ugp/{player_id}.flac`, `.mp3`, `.aac` routes on the streams controller for member connections
  - **How UGP streaming works**: `UGPStream` class in `ugp_stream.py` — has an `audio_source` (async generator), subscribers (per-member callbacks), multicasts bytes from the source to all subscribers. Each member gets its own FFmpeg-transcoded stream via `get_ffmpeg_stream`.
  - **No native sync protocol needed**: Any player that can receive HTTP audio can join a universal group
  - **Member management**: Same pattern as sync group — `CONF_GROUP_MEMBERS`, `CONF_DYNAMIC_GROUP_MEMBERS`, `create_group_player`/`remove_group_player`
  - Note: There is no `README.md` for universal_group (unlike sync_group). This architecture doc fills that gap.

  **c. Ad-hoc sync** (direct `set_members` on a physical player):
  - **No persistent group entity** — the parent player directly manages group membership
  - Triggered via `cmd_group(player_id, target_player)` / `cmd_ungroup(player_id)` or `cmd_set_members`
  - The parent player's `group_members` list grows/shrinks, and the child players' `synced_to` points to the parent
  - `cmd_group` is a convenience: adds `player_id` to `target_player`'s members. `cmd_group_many` adds multiple children.
  - Queue belongs to the parent player (the sync leader), not a separate group entity
  - **Dissolves when stopped** — temporary, unlike sync groups
  - The actual `set_members` call goes through `_handle_set_members` in the controller, which validates compatibility, auto-powers members, and handles edge cases (dissolving if target is removed from itself)

- **`_handle_set_members` and `_handle_set_members_with_protocols`**: The two-phase set_members logic:
  1. `_handle_set_members`: Validates players, checks `can_group_with`, handles ungroup-if-already-synced, powers on children. For `GROUP` players, delegates directly to `player.set_members()`. For regular players, calls `_handle_set_members_with_protocols`.
  2. `_handle_set_members_with_protocols`: Translates visible player IDs to protocol player IDs when the parent has an active output protocol, then forwards to the appropriate protocol player's `set_members`. This is the bridge between the user-visible player model and the underlying protocol reality.

- **The three relationship properties — often confused**:
  - `group_members` (list of player_ids): On a sync leader or group player, lists all members including self (for non-GROUP types). On a regular player, empty unless ad-hoc synced.
  - `synced_to` (str | None): On a child player synced to a leader, points to the leader. GROUP type always returns None.
  - `active_group` (str | None): On any player, the ID of the currently active (playing/paused) GROUP player this player belongs to. Computed by scanning all GROUP players.
  
  Explain how these three interact. A player can have `synced_to` set (synced to an ad-hoc leader) AND `active_group` set (part of a playing GROUP). But `synced_to` and `group_members` are from different perspectives — `synced_to` is the child's view, `group_members` is the leader's view.

- **`__final_group_members`**: How it resolves the final group member list — translates protocol player IDs to visible player IDs via `_translate_protocol_ids_to_visible`, includes active output protocol's group members, ensures self is first for non-GROUP types.

- **`__final_synced_to`**: How it resolves — checks native `synced_to` first, then checks if any linked protocol player is synced (translating protocol IDs to visible parents).

- **`__final_active_group`**: Scans all available GROUP players to find one that is playing/paused and includes this player in its members.

- **`iter_group_members`**: The controller helper that iterates children of a group player with filtering (only_powered, only_playing, active_only, exclude_self).

- **`_get_player_groups`**: Returns all GROUP players a given player belongs to.

**Key source files:**
- `music_assistant/providers/sync_group/` — `player.py` (~539 lines), `provider.py`, `constants.py`, `README.md`
- `music_assistant/providers/universal_group/` — `player.py` (~454 lines), `provider.py`, `ugp_stream.py` (~124 lines), `constants.py`
- `music_assistant/controllers/players/controller.py` — `cmd_set_members`, `cmd_group`, `cmd_ungroup`, `_handle_set_members`, `_handle_set_members_with_protocols`, `iter_group_members`, `_get_player_groups`
- `music_assistant/models/player.py` — `group_members`, `synced_to`, `active_group` (properties), `__final_group_members`, `__final_synced_to`, `__final_active_group`

### 2. `docs/architecture/07-volume.md` — Volume Control

Individual and group volume, the additive-delta algorithm, plugin volume callbacks, and known issues.

**Must cover:**

- **Individual volume routing** (recap from `04-player-controller.md`, but focused on the volume path):
  `_handle_cmd_volume_set` resolves through `volume_control` config:
  - `NATIVE` → `player.volume_set(volume_level)`
  - `FAKE` → stores in `extra_data[ATTR_FAKE_VOLUME]`, triggers `update_state()`
  - `NONE` → raises `UnsupportedFeaturedException`
  - Specific player/control ID → delegates to that entity
  
  Before setting: auto-unmutes if muted (unless `ATTR_MUTE_LOCK` is set). Always resets fake mute.

- **Group volume — the additive-delta algorithm** (`set_group_volume` in controller):
  1. Read current `group_volume` (average of powered members' volume levels)
  2. Compute `volume_dif = target_volume - group_volume`
  3. Apply `volume_dif` to each powered member: `new_child_volume = cur_child_volume + volume_dif`
  4. Clamp to [0, 100]
  5. Execute all child volume sets concurrently via `asyncio.gather`
  
  **Why additive-delta**: Preserves relative volume differences between speakers. If living room is at 60 and kitchen at 40, setting group volume to 55 (from 50 average) adds +5 to both → 65 and 45.
  
  **Clamping/drift behavior**: If a child is at 95 and delta is +10, it clamps to 100 — losing 5 units. The inverse operation won't restore the original ratio. The maintainer considers this acceptable for the use case. Note this as a known characteristic.
  
  Skips members with `volume_control == PLAYER_CONTROL_NONE`.

- **`group_volume` property** (in Player model): Computed, not stored. For non-group players with no group_members, returns `self.state.volume_level`. For group/sync leaders, computes average of powered members' volume levels (via `iter_group_members`). Returns None if no members support volume.

- **`group_volume_muted` property**: Similar pattern — for groups, True only if ALL powered members are muted. False if at least one is unmuted. None if no members support mute.

- **Group volume up/down** (`cmd_group_volume_up`, `cmd_group_volume_down`): Computes ±5 steps from current `group_volume`, delegates to `set_group_volume`. The step size 5 is hardcoded.

- **Group mute** (`cmd_group_volume_mute`): Iterates powered group members, sets `ATTR_MUTE_LOCK` on each (to prevent auto-unmute during subsequent volume changes), then mutes/unmutes each member.

- **Plugin volume callbacks**: When `_handle_cmd_volume_set` runs, before handling native/fake/delegate volume, it checks `_get_active_plugin_source(player)`. If a `PluginSource` is active for this player AND it has an `on_volume` callback, the callback is invoked with the volume level. This runs IN ADDITION TO the normal volume handling — it's not either/or.
  
  The `PluginSource.on_volume` callback (defined in `music_assistant/models/plugin.py`) is `Callable[[int], Awaitable[None]] | None`.
  
  `_get_active_plugin_source` matches by `in_use_by == player.player_id` OR `player.state.active_source == plugin_source.id`.
  
  **The `in_use_by` gap for groups**: `in_use_by` stores a single `player_id`. For group players, the group player ID is set, but individual child players within the group don't have `in_use_by` set to them — the plugin doesn't know about individual children. This means plugin volume callbacks only fire for the group player, not for individual member volume changes. This is a known architectural limitation.

- **Volume during announcements**: The announcement flow saves current volume, adjusts to announcement volume (via `get_announcement_volume` — supports absolute, relative, percentual strategies with min/max clamping), plays the announcement, then restores the previous volume. The announcement volume strategy is per-player config.

- **Mute lock mechanism**: `ATTR_MUTE_LOCK` in `extra_data` prevents auto-unmute during group volume changes. Set when individually muting a player within a group. Cleared when explicitly unmuting. This prevents a group volume change from un-muting a player the user specifically muted.

**Key source files:**
- `music_assistant/controllers/players/controller.py` — `cmd_volume_set`, `cmd_volume_up`, `cmd_volume_down`, `cmd_group_volume`, `cmd_group_volume_up`, `cmd_group_volume_down`, `cmd_group_volume_mute`, `set_group_volume`, `_handle_cmd_volume_set`, `_get_active_plugin_source`, `get_announcement_volume`
- `music_assistant/models/player.py` — `group_volume`, `group_volume_muted` properties, `volume_level`, `volume_muted`
- `music_assistant/models/plugin.py` — `PluginSource` (especially `on_volume`, `in_use_by`)

## Writing Principles

Same as prior sub-plans:
- Cite code, not assumptions. Every claim backed by file + method/class name.
- Explain the "why", not just the "what". Use git history where helpful.
- Flag known gaps honestly (especially the volume drift and `in_use_by` gap).
- Keep it skimmable: Mermaid diagrams, tables, short code snippets.
- Human voice, no AI filler.

## Exploration Strategy

1. **Start with `providers/sync_group/player.py`** — read end-to-end. This is the most important file for understanding how sync groups work. Focus on: `_form_syncgroup()`, `_dissolve_syncgroup()`, `_sync_leader_selection()`, `play_media()`, `set_members()`, `stop()`, feature inheritance.
2. **Read `providers/sync_group/provider.py`** — creation/removal logic, `discover_players()`.
3. **Read `providers/sync_group/README.md`** — thorough existing documentation. Verify every claim against code. This README was recently updated and is high quality — use it as a starting reference but don't trust it blindly.
4. **Read `providers/sync_group/constants.py`** — `EXTRA_FEATURES_FROM_MEMBERS`, `SGP_PREFIX`, member filter config.
5. **Read `providers/universal_group/player.py`** — the UGP player implementation. Focus on: `play_media()`, `_serve_ugp_stream()`, `_set_attributes()`, member management, `requires_flow_mode`, the dynamic route registration.
6. **Read `providers/universal_group/ugp_stream.py`** — the multicast stream implementation. Small file (~124 lines). Understand the subscriber model and how audio is distributed.
7. **Read `providers/universal_group/provider.py`** — creation/removal, `discover_players()`.
8. **Read the grouping-related methods in `controllers/players/controller.py`**:
   - `cmd_set_members`, `cmd_group`, `cmd_group_many`, `cmd_ungroup`, `cmd_ungroup_many` — the public API surface
   - `_handle_set_members`, `_handle_set_members_with_protocols` — the implementation with protocol translation
   - `set_group_volume`, `cmd_group_volume`, `cmd_group_volume_up`, `cmd_group_volume_down`, `cmd_group_volume_mute` — group volume
   - `iter_group_members`, `_get_player_groups` — helper methods
   - `_handle_cmd_volume_set` — individual volume with plugin callback
   - `_get_active_plugin_source` — plugin source resolution
9. **Read the group-related properties in `models/player.py`**:
   - `group_members`, `synced_to`, `active_group` (base properties)
   - `group_volume`, `group_volume_muted` (computed properties)
   - `__final_group_members`, `__final_synced_to`, `__final_active_group` (final computed properties)
10. **Read `models/plugin.py`** — `PluginSource` dataclass, especially the callback fields (`on_volume`, `on_play`, `on_pause`, etc.) and `in_use_by`.
11. **Git history**: 
    - `git log --oneline -20 music_assistant/providers/sync_group/player.py`
    - `git log --oneline -20 music_assistant/providers/universal_group/player.py`
    - `git log --oneline -20 music_assistant/controllers/players/controller.py` (look for group/volume changes)
    - Check PRs mentioned in the master plan: #3534 (select_source ungroup), #3343 (Cast + sync groups), #3277 (volume_up/down for groups), #3399 and #3512 (our PRs — maintainer feedback)

## Reconciliation with Sub-plan 1-2

This is the most important reconciliation pass. Grouping is the most cross-cutting concern in the codebase.

### Step 1 — Before exploring (structural vocabulary only)

Skim section headings and terminology from all 7 prior docs. Note the vocabulary used for `PlayerType`, `group_members`, `synced_to`, command routing, events, protocol linking. Do NOT read interpretive claims about how grouping works.

### Step 2 — After writing your own docs

Read all 7 prior documents in full. This is the highest-risk reconciliation because grouping touches almost everything. Specific checks:

- **`03-player-model.md`**: Does it accurately describe `group_members`, `synced_to`, `active_group`, `group_volume`? These properties have subtle semantics that are only fully clear after understanding the three grouping models. Expect to find corrections or missing nuance here. In particular:
  - Does it explain when `group_members` is non-empty for non-GROUP types (ad-hoc sync)?
  - Does it explain the difference between `synced_to` (child's view) and `group_members` (leader's view)?
  - Does `__final_group_members` documentation match what you found about protocol ID translation?

- **`04-player-controller.md`**: Does it correctly describe group-related command routing? Does `cmd_set_members` need more detail about the two-phase protocol translation? Does it need forward references to `06-grouping.md`?

- **`05-protocol-linking.md`**: Does it correctly describe the interaction between protocol linking and grouping? Specifically `_handle_set_members_with_protocols` — does the protocol linking doc mention that set_members translates visible player IDs to protocol player IDs?

- **`15-provider-lifecycle.md`**: Does it mention `sync_group` and `universal_group` as builtin provider types? Are they listed in the examples?

- **`01-event-system.md`**: Does it cover the events that drive group state changes? Are `PLAYER_UPDATED` events fired when group membership changes?

- **`02-configuration.md`**: Does it describe how player config persists group membership (`CONF_GROUP_MEMBERS`)? Does `group_volume` appear anywhere in config (it shouldn't — it's computed, not stored)?

### Step 3 — Bidirectional revision

Fix errors in prior docs where found. Then critically check the reverse direction:

- If `02-configuration.md` describes how player config is persisted, does that change the understanding of where group membership state lives (it's in config for static groups, in memory for ad-hoc sync)?
- If `04-player-controller.md` describes `_get_player_with_redirect`, does that change the understanding of how commands reach group players (sync leader redirect vs direct GROUP dispatch)?
- If `05-protocol-linking.md` describes protocol selection, does that affect understanding of how sync groups choose which protocol to use for the sync leader?

If so, revise `06-grouping.md` and `07-volume.md` accordingly.

### Step 4 — Cascade check

Re-read all revisions (both directions) and confirm internal consistency. If revising `03-player-model.md` changed something about `__final_group_members`, verify that `04-player-controller.md` and `06-grouping.md` are still consistent with the revision.

## What NOT to Cover

These topics belong to later sub-plans. Mention only in passing with forward references:

- **Plugin system internals**: `PluginSource` callbacks are covered in volume context, but full plugin architecture is Sub-plan 5. Don't explain how plugins load, register, or provide audio sources.
- **Queue management**: How queues interact with groups (which entity owns the queue) is mentioned briefly but detailed queue management is Sub-plan 4.
- **UGP streaming pipeline details**: How audio flows through FFmpeg, the AudioBuffer, smart fades — that's Sub-plan 4. Sub-plan 3 covers UGPStream's multicast subscriber model but not the audio processing pipeline that feeds it.
- **Party plugin**: The `party` provider is a PluginProvider for guest access, not a grouping mechanism. It belongs in Sub-plan 5.

## Output Format

Same format as prior sub-plans:
- One-paragraph summary opening each document
- `##` headers for major sections
- At least one Mermaid diagram per document (sync group formation flow, volume routing flow, and the three-way relationship between `group_members`/`synced_to`/`active_group` are good candidates)
- Tables for comparisons (sync group vs universal group vs ad-hoc sync is the essential comparison table)
- Short code snippets for essential signatures
- "Key Files" section at the end of each document
- Cross-references to other architecture docs

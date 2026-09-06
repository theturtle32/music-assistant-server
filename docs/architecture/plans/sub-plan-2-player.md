# Sub-plan 2: Player Model and Controller

**Scope**: The Player abstraction (the most complex model in the system), the PlayerController command surface, and protocol linking.

**Context**: Sub-plan 1 has been executed. Four architecture docs exist under `docs/architecture/`: `00-overview.md`, `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`. This sub-plan builds on that foundation and reconciles with it at the end.

## Deliverables

You will produce 3 markdown files under `docs/architecture/`.

### 1. `docs/architecture/03-player-model.md` — The Player Abstraction

The Player model is the most complex single class in the codebase (~2142 lines). This document must make it understandable.

**Must cover:**

- **The `_attr_` pattern**: The `Player` ABC defines dozens of `_attr_*` class attributes (e.g., `_attr_type`, `_attr_volume_level`, `_attr_playback_state`, `_attr_group_members`) with matching `@property` accessors. Provider implementations set these attributes to report state. This pattern is modeled after Home Assistant's Entity model — confirm this via the docstring and structure. List the major `_attr_*` groups: identity/type, playback state, volume/mute, group membership, device info/identifiers, source/media, polling config, UI defaults.

- **`Player` (runtime, mutable) vs `PlayerState` (API snapshot)**: The `Player` class is the live, mutable internal model used by providers and the controller. `PlayerState` (aliased from `music_assistant_models.player.Player`) is a frozen dataclass snapshot for API consumers. The `state` property returns the latest snapshot. The `update_state()` method recalculates the snapshot from current `_attr_*` values, diffs against the previous snapshot, and signals `PLAYER_UPDATED` if anything changed. Explain the caching mechanism: `_cache` dict is cleared on every `update_state()` call, and `@cached_property` (from `propcache`) is used for expensive computed properties.

- **`__final_*` computed properties**: These `@cached_property @final` methods compute the "effective" value of a player attribute after applying overrides from player controls, sync groups, active output protocols, and config. There are 12 of them:
  - `__final_playback_state` — uses active output protocol's state, or sync leader's state, or native state
  - `__final_power_state` — resolves through power_control config (NATIVE, FAKE, NONE, or a specific player/control ID)
  - `__final_volume_level` — resolves through volume_control config (same pattern as power)
  - `__final_volume_muted_state` — resolves through mute_control config
  - `__final_active_group` — which group player this player is currently part of
  - `__final_current_media` — media from sync leader or active group if synced
  - `__final_source_list` — merges native sources with linked protocol sources
  - `__final_group_members` — resolves through the group data owner pattern
  - `__final_synced_to` — which player this player is synced to (sync leader)
  - `__final_supported_features` — merges features from linked output protocols
  - `__final_can_group_with` — which other players this one can group with
  - `__final_active_source` — resolves the effective active source

  Focus on the **resolution chain** — what data source takes precedence over what. Use a table or diagram.

- **PlayerType taxonomy**: `PLAYER` (native vendor device), `PROTOCOL` (generic protocol endpoint, hidden in UI), `GROUP` (multi-speaker group), `STEREO_PAIR`. Explain what code paths branch on type — e.g., `synced_to` returns None for GROUP, protocol players are excluded from `all_players()` by default.

- **Player control commands**: The abstract methods providers must implement — `play()`, `stop()`, `pause()`, `volume_set()`, `power()`, `volume_mute()`, `next_track()`, `play_media()`, `play_announcement()`, `set_members()`, `select_source()`, `select_sound_mode()`, `set_option()`. Show which are gated by `PlayerFeature` flags.

- **`_check_feature_with_active_protocol` and `_get_protocol_player_for_feature`**: How the player checks features considering the active output protocol, and how it finds the best protocol player for a given feature. Explain the control priority ordering for non-active protocols (chromecast > dlna > airplay > sendspin).

- **`update_state()` method**: The central state update pipeline — clears cached properties, calls `__calculate_player_state()`, diffs against previous state, debounces media change callbacks, persists default name changes, schedules `_on_player_media_updated`, and signals events.

- **Protocol linking state**: `linked_output_protocols`, `protocol_parent_id`, `active_output_protocol`, `output_protocols` — how these relate to each other and to the protocol linking system (detailed in `05-protocol-linking.md`).

**Key source files:**
- `music_assistant/models/player.py` (~2142 lines) — the entire Player class
- `music_assistant_models.player` (installed package) — `PlayerState`, `DeviceInfo`, `OutputProtocol`, `PlayerMedia`, `PlayerSource`, `PlayerSoundMode`, `PlayerOption`
- `music_assistant_models.enums` — `PlayerType`, `PlayerFeature`, `PlaybackState`, `IdentifierType`

### 2. `docs/architecture/04-player-controller.md` — The PlayerController

The command routing hub that sits between API consumers and player implementations.

**Must cover:**

- **Registration flow**: `register(player)` acquires `_register_lock`, checks for duplicates, stores in `_players` dict, calls `player.update_state()`, signals `PLAYER_ADDED`, then triggers protocol link evaluation. `unregister(player_id, permanent)` handles cleanup — ungroup, cancel timers, remove config if permanent, signal `PLAYER_REMOVED`.

- **Command routing — the two-tier pattern**: Public `cmd_*` methods are the API surface (decorated with `@api_command`). They handle permission checks, logging, power-on-demand, and command locking via `handle_player_command` decorator. Private `_handle_cmd_*` methods contain the actual implementation logic. List the full command surface:
  - Transport: `cmd_stop`, `cmd_play`, `cmd_pause`, `cmd_play_pause`, `cmd_resume`, `cmd_seek`, `cmd_next_track`, `cmd_previous_track`
  - Volume: `cmd_volume_set`, `cmd_volume_up`, `cmd_volume_down`, `cmd_volume_mute`
  - Group volume: `cmd_group_volume`, `cmd_group_volume_up`, `cmd_group_volume_down`, `cmd_group_volume_mute`
  - Group membership: `cmd_set_members`, `cmd_group`, `cmd_group_many`, `cmd_ungroup`, `cmd_ungroup_many`
  - Power: `cmd_power`

- **`_get_player_with_redirect`**: The central command routing mechanism — if a player is synced to a sync leader, playback commands are redirected to the leader. Explain why this exists and when redirection happens.

- **Power management**: `_handle_cmd_power` — fake power (stores in `extra_data`), native power, protocol-player-as-power-control, external `PlayerControl` as power control. Power-on demand: the `handle_player_command` decorator auto-powers on the player before executing play-related commands. Auto-play on power on (config-driven).

- **Volume routing**: `_handle_cmd_volume_set` — resolves through `volume_control` config (NATIVE, FAKE, or specific player/control ID). For group players, delegates to `set_group_volume`. Group volume commands route to child members. Explain the flow for a volume command hitting a grouped player.

- **Player polling**: `_poll_players` background task — runs on a 1-second tick, calls `player.poll()` for players with `needs_poll=True` at their configured `poll_interval`. Also polls elapsed time for active players.

- **Announcement handling**: `cmd_play_announcement` and `_handle_play_announcement` — the complex flow of saving state, adjusting volume, playing the announcement, restoring state. Mention the `AnnounceData` helper from `helpers.py`.

- **`select_source` and active source management**: How `cmd_select_source` works, the relationship between `active_source` on the player and the queue/plugin source system (forward reference to Sub-plan 3 for plugin details, Sub-plan 4 for queue details).

- **Concurrency controls**: `_player_throttlers` (per-player update throttling), `_player_command_locks` (per-player command serialization), `_register_lock` (registration serialization), `_delayed_evaluation_lock` (protocol evaluation serialization), `IN_QUEUE_COMMAND` ContextVar (prevents circular calls between players and player_queues controllers).

- **Player config**: How the controller interacts with the ConfigController for player settings — `get_player_config`, `save_player_config`, the `update_config` callback. Categories: "generic", "playback", "protocol_generic", "announcements", "player_controls".

**Key source files:**
- `music_assistant/controllers/players/controller.py` (~3242 lines) — the main controller
- `music_assistant/controllers/players/helpers.py` — `handle_player_command` decorator, `AnnounceData`, `wait_for_power_on`
- `music_assistant/models/player_provider.py` — the `PlayerProvider` base class that providers implement

### 3. `docs/architecture/05-protocol-linking.md` — Multi-Protocol Device Merging

How multiple protocol endpoints for the same physical device are unified into a single visible player.

**Must cover:**

- **The problem**: A Samsung soundbar might appear as 3 separate players (AirPlay, Chromecast, DLNA). Protocol linking merges them.

- **`ProtocolLinkingMixin`**: Mixin class on `PlayerController` in `music_assistant/controllers/players/protocol_linking.py` (~1870 lines). Explain the mixin pattern — it expects `self.mass`, `self._players`, `self.logger`, `self.get_player()`, etc.

- **Identifier matching hierarchy** (from `IdentifierType` enum, in order of reliability):
  1. `MAC_ADDRESS` — most reliable, ARP-verified when possible
  2. `SERIAL_NUMBER`
  3. `UUID`
  4. `CAST_UUID` / `AIRPLAY_ID` — protocol-specific stable IDs
  5. `IP_ADDRESS` — last resort, only when strong identifiers are unavailable
  6. `player_id` — fallback device key for players without identifiers (e.g., Sendspin)

  Key constraint: Players from the **same protocol domain** are never matched, even with identical identifiers (handles multiple software instances on the same host).

- **The linking flows** (3 distinct scenarios):
  1. **Protocol player registers, native player already exists**: `_try_link_protocol_to_native` — immediate linking, protocol player hidden, added to native's `output_protocols`
  2. **Protocol player registers, no native player**: `_schedule_protocol_evaluation` — delayed (15s standard, 45s if previously linked), then `_create_or_update_universal_player` groups matching protocols under a `UniversalPlayer`
  3. **Native player registers after universal player exists**: `_check_replace_universal_player` — transfers protocol links from universal to native, removes universal player

- **UniversalPlayer**: Virtual player type from `music_assistant/providers/universal_player/`. Created for devices without native vendor support. Wraps one or more protocol players. Features: no native `PLAY_MEDIA` (delegates to protocol players), aggregates features from linked protocols, unified control surface.

- **Output protocol selection** (`_select_best_output_protocol`): Priority chain — grouped protocol first, then user preference (`CONF_PREFERRED_OUTPUT_PROTOCOL`), then native `PLAY_MEDIA`, then best available by protocol priority (`PROTOCOL_PRIORITY` from constants: airplay=10, squeezelite=20, chromecast=30, sendspin=40, dlna=50).

- **Persistence**: `CONF_LINKED_PROTOCOL_IDS` stores linked protocol player IDs in parent player's config for fast restart. `CONF_PROTOCOL_PARENT_ID` stores the parent player ID on each protocol player. On restart, cached links are restored immediately without waiting for re-evaluation.

- **MAC address handling**: ARP-based MAC resolution via `enrich_device_mac_address`, locally administered MAC detection (`is_locally_administered_mac`), MAC normalization for matching (`normalize_mac_for_matching`). Why this matters: some devices report incorrect or locally administered MACs; ARP provides the real hardware address.

- **GROUP and STEREO_PAIR exclusion**: These player types are excluded from protocol linking entirely — they represent logical groupings, not physical devices.

**Key source files:**
- `music_assistant/controllers/players/protocol_linking.py` (~1870 lines) — the mixin
- `music_assistant/providers/universal_player/` — `UniversalPlayer`, `UniversalPlayerProvider`
- `music_assistant/controllers/players/README.md` — existing documentation (verify against code, incorporate rather than duplicate)
- `music_assistant/helpers/util.py` — `enrich_device_mac_address`, `is_valid_mac_address`, `is_locally_administered_mac`, `normalize_mac_for_matching`
- `music_assistant/constants.py` — `PROTOCOL_PRIORITY`, `PROTOCOL_FEATURES`, `ACTIVE_PROTOCOL_FEATURES`, `CONF_LINKED_PROTOCOL_IDS`, `CONF_PROTOCOL_PARENT_ID`, `CONF_PREFERRED_OUTPUT_PROTOCOL`

## Writing Principles

Same as Sub-plan 1:
- Cite code, not assumptions. Every claim backed by file + method/class name.
- Explain the "why", not just the "what". Use git history where helpful.
- Flag known gaps honestly.
- Keep it skimmable: Mermaid diagrams for flows, tables for comparisons, short code snippets.
- Human voice, no AI filler.

## Exploration Strategy

1. **Start with `models/player.py`** — read it end-to-end. This is the largest and most complex model. Focus on: `_attr_*` pattern, property accessors, abstract command methods, `update_state()`, `__calculate_player_state()`, all `__final_*` methods, protocol linking state properties.
2. **Read `controllers/players/controller.py`** — focus on: class structure, `register`/`unregister`, all `cmd_*` methods, all `_handle_cmd_*` methods, `_get_player_with_redirect`, `_poll_players`, `select_source`.
3. **Read `controllers/players/helpers.py`** — understand `handle_player_command` decorator and `AnnounceData`.
4. **Read `controllers/players/protocol_linking.py`** — the entire mixin. Focus on: `_evaluate_protocol_links`, `_try_link_protocol_to_native`, `_schedule_protocol_evaluation`, `_create_or_update_universal_player`, `_check_replace_universal_player`, `_select_best_output_protocol`, identifier matching logic.
5. **Read `controllers/players/README.md`** — existing documentation. Verify every claim against what you found in the code. Incorporate accurate content, correct inaccuracies.
6. **Read `models/player_provider.py`** — the PlayerProvider ABC that providers implement. Understand: `discover_players`, `play_media`, `play_announcement`, `set_members`.
7. **Skim `providers/universal_player/`** — understand `UniversalPlayer` class, how it wraps protocols, its lifecycle.
8. **Git history**: `git log --oneline -20 music_assistant/controllers/players/protocol_linking.py` and `git log --oneline -20 music_assistant/models/player.py` for recent structural changes. Look for PRs #3294, #3284, #3300 (protocol linking evolution).

## Reconciliation with Sub-plan 1

### Step 1 — Before exploring (structural vocabulary only)

Skim the section headings and key terms from the 4 existing docs. Pick up:
- Controller names and startup order from `00-overview.md`
- Event categories (especially Player events) from `01-event-system.md`
- Config hierarchy and player config structure from `02-configuration.md`
- Provider lifecycle phases from `15-provider-lifecycle.md`

Do NOT read interpretive content at this stage.

### Step 2 — After writing your own docs

Read all 4 Sub-plan 1 docs in full. Compare your independently formed understanding against their claims. Specific checks:

- Does `00-overview.md`'s component map row for PlayerController accurately describe what you found? Is the one-sentence description sufficient?
- Does `00-overview.md`'s startup lifecycle correctly place when player registration happens (it happens during provider loading, steps 12-13)?
- Does `01-event-system.md`'s table of Player events match what you see the PlayerController actually signaling? Are there events the controller emits that aren't listed?
- Does `02-configuration.md` correctly describe PlayerConfig? Does it mention the config categories ("generic", "playback", "protocol_generic", "announcements", "player_controls")? Does it describe how `requires_reload` works for player config changes?
- Does `15-provider-lifecycle.md` correctly describe how PlayerProviders are loaded, and the `players.on_provider_loaded()` / `players.on_provider_unload()` callbacks?

### Step 3 — Bidirectional revision

Fix errors in Sub-plan 1 docs where found. Also check the reverse direction: does Sub-plan 1's description of the event system or config system recontextualize how the player model works? For example:
- Does the event system doc's explanation of sync vs async dispatch clarify how `PLAYER_UPDATED` events are handled?
- Does the config doc's description of encrypted values or config change propagation affect understanding of how player config changes reach the player?

If you revise any Sub-plan 1 docs, note what you changed and why.

### Step 4 — Cascade check

If your own docs were significantly revised in Step 3, re-read the revisions to Sub-plan 1 docs and confirm they are still consistent.

## What NOT to Cover

These topics belong to later sub-plans. Mention only in passing with forward references:

- **Grouping internals**: Sync groups, universal groups, ad-hoc sync, `_resolve_group_data_owner`, group volume algorithms (Sub-plan 3). You will reference `group_members`, `synced_to`, `active_group` as Player properties, but do NOT explain the three grouping models or how group volume works.
- **Plugin/PluginSource**: `select_source` interacts with plugins, but plugin internals are Sub-plan 5. Use forward references.
- **Queue management**: The queue as "active source" is referenced but detailed in Sub-plan 4.
- **Streaming pipeline**: How audio reaches players after commands are issued (Sub-plan 4).

If you find yourself writing more than 2-3 sentences about any of these topics, stop and add a forward reference instead.

## Output Format

Same format as Sub-plan 1:
- One-paragraph summary opening each document
- `##` headers for major sections
- At least one Mermaid diagram per document where a flow is complex (command routing flow, protocol linking flow, `__final_*` resolution chain are all good candidates)
- Tables for comparisons (PlayerType taxonomy, cmd_* vs _handle_cmd_* mapping, __final_* properties)
- Short code snippets for essential signatures
- "Key Files" section at the end of each document
- Cross-references to other architecture docs

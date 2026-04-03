# 06 — Grouping Architecture

Music Assistant supports three distinct grouping models for multi-room audio: **sync groups**, **universal groups**, and **ad-hoc sync**. Each differs in persistence, protocol requirements, and how audio reaches the speakers. All three converge on the same underlying player properties — `group_members`, `synced_to`, and `active_group` — but populate them through fundamentally different mechanisms. This document explains each model, their formation and dissolution lifecycles, and how the controller bridges the user-visible player world with the underlying protocol reality.

## The Three Grouping Models

| | Sync Group | Universal Group | Ad-hoc Sync |
|---|---|---|---|
| **Provider** | `sync_group` | `universal_group` | *(none — native)* |
| **PlayerType** | `GROUP` | `GROUP` | Parent's type (usually `PLAYER`) |
| **Persistent entity** | Yes | Yes | No |
| **Queue ownership** | Group player | Group player | Parent player (sync leader) |
| **Cross-protocol** | No — same protocol only | Yes — any player | No — same protocol only |
| **Audio delivery** | Delegated to sync leader's native protocol | Server-side fan-out (independent HTTP stream per member) | Native protocol sync |
| **Player ID format** | `syncgroup_{random_8}` | `ugp_{random_8}` | N/A |
| **Dissolves on stop** | After 5s delay | No (persistent power state) | Immediately |
| **Dynamic membership** | Optional (`CONF_DYNAMIC_GROUP_MEMBERS`) | Optional | Always |
| **`SET_MEMBERS` feature** | Only if dynamic | Only if dynamic | Depends on provider |

## Sync Groups

Sync groups are persistent group players that delegate playback to a member's native sync protocol. Created through `SyncGroupProvider.create_group_player()`, each group gets its own player ID (`syncgroup_` prefix) and queue, but never touches audio directly.

**Key class:** `SyncGroupPlayer` (`music_assistant/providers/sync_group/player.py`)

### Sync Leader

The central concept. A sync group selects one member as the **sync leader** — the player that actually receives `play_media`, manages playback state, and syncs the other members to itself via its native protocol (AirPlay-to-AirPlay, Sonos-to-Sonos, etc.).

The sync leader reference is stored as `SyncGroupPlayer.sync_leader: Player | None`.

**Selection logic** (`_select_sync_leader`):

1. If a current leader exists and is available, keep it
2. Prioritize static group members (stable across restarts)
3. Fall back to first available member

### Protocol Compatibility

Only same-protocol players can be grouped in a sync group. Enforcement happens through `can_group_with`:

- **Static groups**: return the configured static members directly
- **Dynamic groups with a leader**: return the leader's `can_group_with` minus any filtered members
- **Dynamic groups with members but no leader**: use the first available member's `can_group_with`
- **Empty dynamic groups**: scan all available players that support `SET_MEMBERS` and have `can_group_with`

A `CONF_MEMBERS_FILTER` config entry allows excluding specific players from the grouping options.

### Static vs Dynamic Groups

**Static** groups have fixed membership defined at creation in `CONF_GROUP_MEMBERS`. Members always rejoin when playback starts and cannot be removed at runtime. The `SET_MEMBERS` feature is not advertised.

**Dynamic** groups (`CONF_DYNAMIC_GROUP_MEMBERS = True`) support runtime `SET_MEMBERS` calls. Static members still cannot be removed, but additional members can join or leave freely.

### Feature Inheritance

Base features are minimal — just `PLAY_MEDIA` (plus `SET_MEMBERS` if dynamic). When a sync leader is active, the group inherits additional features from the leader:

```python
EXTRA_FEATURES_FROM_MEMBERS = {
    PlayerFeature.ENQUEUE,
    PlayerFeature.GAPLESS_PLAYBACK,
    PlayerFeature.VOLUME_SET,
    PlayerFeature.VOLUME_MUTE,
    PlayerFeature.MULTI_DEVICE_DSP,
}
```

This means a sync group's capabilities change dynamically depending on which member is elected leader.

### State Delegation

The sync group delegates most of its observable state to the sync leader:

| Property | Source |
|---|---|
| `playback_state` | Sync leader (or `IDLE` if none) |
| `elapsed_time` | Sync leader (or its active protocol player) |
| `current_media` | Sync leader |
| `active_source` | Sync leader (with protocol-awareness — see below) |
| `group_members` | Sync leader's reported members (preferred) or internal list |
| `source_list` | Sync leader |

The `elapsed_time` property is protocol-aware: if the sync leader has an active output protocol (not native), elapsed time is read from the protocol player instead.

The `active_source` property filters out cases where the sync leader reports a source that actually belongs to an active output protocol (e.g. AirPlay) or a bridged protocol (e.g. Sendspin), to avoid confusing source attribution.

### Formation Lifecycle

```mermaid
flowchart TD
    A[play_media called on SyncGroupPlayer] --> B[_form_syncgroup]
    B --> C[Cancel any pending dissolve timer]
    C --> D[Ensure static members are in group_members]
    D --> E{sync_leader exists?}
    E -- No --> F[_select_sync_leader]
    F --> G{Leader found?}
    G -- No --> H[Return — empty group]
    G -- Yes --> I[Set sync_leader]
    E -- Yes --> I
    I --> J[Reorder: leader first in group_members]
    J --> K{Members need syncing?}
    K -- No --> L[Done]
    K -- Yes --> M{Leader currently playing?}
    M -- Yes --> N[Stop leader first]
    N --> O[cmd_set_members on leader]
    M -- No --> O
    O --> L
    L --> P[play_media forwarded to sync leader via _handle_play_media]
```

The `_form_syncgroup` method is locked (`@lock` decorator from `music_assistant.helpers.util`) to prevent concurrent formation attempts.

### Dissolution Lifecycle

When `stop()` is called on the sync group:

1. Clear `current_media`
2. Stop the sync leader via `_handle_cmd_stop` (bypasses group redirect to avoid infinite loop)
3. Schedule `_dissolve_syncgroup` with a **5-second delay** (`call_later`)

The 5-second delay prevents unnecessary sync/unsync churn during track transitions, where the queue briefly stops between tracks.

`_dissolve_syncgroup` (also locked):

1. Get all sync children from the leader's `group_members`
2. Call `cmd_set_members` on the leader to remove all children
3. Clear `sync_leader` to `None`
4. Trigger state update

### Dynamic Member Changes

When `set_members` is called on a dynamic group during playback:

- **Adding members**: Validates compatibility with the sync leader's `can_group_with`, adds to internal list, forwards to `cmd_set_members` on the leader
- **Removing the sync leader**: Stops playback, dissolves the group, removes the old leader from the member list, selects a new leader, and resumes playback
- **Removing last member**: Dissolves the group entirely
- **Removing a regular member**: Forwards removal to `cmd_set_members` on the leader
- **Static members cannot be removed** — raises `PlayerCommandFailed`

## Universal Groups

Universal groups solve the cross-protocol problem. Any player that can receive HTTP audio can participate, regardless of its native protocol. Audio synchronization is best-effort since there's no shared clock across protocols.

**Key class:** `UniversalGroupPlayer` (`music_assistant/providers/universal_group/player.py`)

### Server-Side Fan-Out

Unlike sync groups that delegate to a vendor's native sync protocol, universal groups use `UGPStream` for server-side audio distribution. The MA server reads the audio source, converts it to PCM, then fans it out to each member as an independent unicast HTTP stream (one connection per member, not IP multicast). For the full audio processing pipeline that feeds these streams, see [10-streaming-pipeline.md](10-streaming-pipeline.md).

```mermaid
flowchart LR
    subgraph "MA Server"
        Q[Queue / Audio Source] --> S[UGPStream]
        S --> F1[FFmpeg → FLAC]
        S --> F2[FFmpeg → FLAC]
        S --> F3[FFmpeg → MP3]
    end
    F1 -->|HTTP /ugp/id.flac?player_id=A| PA[Player A]
    F2 -->|HTTP /ugp/id.flac?player_id=B| PB[Player B]
    F3 -->|HTTP /ugp/id.mp3?player_id=C| PC[Player C]
```

Each member connects to a dynamic HTTP route registered at initialization:

- `/ugp/{player_id}.flac`
- `/ugp/{player_id}.mp3`
- `/ugp/{player_id}.aac`

The `player_id` query parameter identifies the requesting member, enabling per-player DSP filter parameters and output format selection.

### UGPStream Internals

The `UGPStream` class (`music_assistant/providers/universal_group/ugp_stream.py`) manages the fan-out:

1. **`_runner()`**: The core loop. Reads from the audio source through FFmpeg (with readrate limiting at 1.1x to prevent excessive buffering), converts to the base PCM format, and pushes each chunk to all subscribers via `asyncio.gather`
2. **`subscribe_raw()`**: Each connecting client gets an `asyncio.Queue(10)` as its subscriber callback. The runner pushes chunks to all queues. An empty `b""` chunk signals stream end.
3. **`get_stream()`**: Wraps `subscribe_raw()` through a second FFmpeg process for per-client transcoding with custom filter parameters (player-specific DSP)

The runner starts lazily — on the first subscriber connection, with a 0.25s delay to allow other subscribers to connect before audio flows.

### Always Flow Mode

Universal groups require flow mode (`requires_flow_mode = True`). This is inherent to the architecture — the server controls the audio stream and members receive it as a continuous flow, not individual track URLs.

### Base Features

Unlike sync groups that inherit features from a leader, universal groups have a fixed feature set:

```python
BASE_FEATURES = {
    PlayerFeature.PLAY_MEDIA,
    PlayerFeature.POWER,
    PlayerFeature.VOLUME_SET,
    PlayerFeature.MULTI_DEVICE_DSP,
}
```

The `volume_set` implementation is a no-op — group volume is handled entirely by the player controller's `set_group_volume` mechanism (see [07-volume.md](07-volume.md)).

### Power and Membership

Power means something different for each grouping model. Sync groups have no native `power()` implementation — they rely on fake power from the controller, and their "on" state is effectively equivalent to "has members and is ready to play." Universal groups implement `power()` directly and use it to manage member lifecycle: power-on activates members (handling collisions with other groups), power-off deactivates and stops them. Ad-hoc sync has no group-level power concept at all — the sync leader's own power state controls the group. For the general power model across all player types, see [03-player-model.md](03-player-model.md#resolution-chains) and [04-player-controller.md](04-player-controller.md#power-management).

Universal groups have explicit power state management:

**Power on:**
1. Reset `group_members` to available static members
2. For each member:
   - Stop if playing something else
   - Handle collision if member belongs to another active group (leave or power off the other group)
   - Ungroup if synced to another player
   - Power on if needed

**Power off:**
1. Stop playback if active
2. Power off all members
3. Reset `group_members` to static list

### Playback Flow

1. `play_media()` → power on → stop existing stream
2. Create `UGPStream` with audio source from `mass.streams.get_stream`
3. Set state optimistically (PLAYING, elapsed_time = 0)
4. Concurrently send `play_media` to each powered, active member with per-member URL:
   `{base_url}/ugp/{player_id}.flac?player_id={member_id}`

State polling (`_set_attributes`, every 30s) grabs playback state and elapsed time from the first active child player.

### State Attributes

Compared to sync groups, the universal group manages its own state more directly:

| Property | Source |
|---|---|
| `playback_state` | First active child member (via polling) |
| `elapsed_time` | First active child member |
| `current_media` | Stored on group itself (deepcopy of media) |
| `group_members` | Internal `_attr_group_members` |
| `synced_to` | Always `None` (GROUP type) |
| `can_group_with` | Static→static member list; Dynamic→`instance_id` of every `PlayerProvider` except the UGP provider itself |

## Ad-hoc Sync

Ad-hoc sync is direct player-to-player grouping with no persistent group entity. The parent player's native `set_members` is called, creating a temporary sync relationship.

### How It Works

- **Triggered by**: `cmd_group(player_id, target_player)`, `cmd_ungroup(player_id)`, or `cmd_set_members`
- **Parent player**: Becomes the sync leader; its `group_members` list grows
- **Child players**: Their `synced_to` points to the parent
- **Queue**: Belongs to the parent player, not a separate entity
- **Dissolves**: When the parent stops or when manually ungrouped

### Controller API

| Method | Description |
|---|---|
| `cmd_group(player_id, target)` | Add `player_id` to `target`'s members |
| `cmd_group_many(target, children)` | Add multiple children (deprecated alias for `cmd_set_members`) |
| `cmd_ungroup(player_id)` | Remove player from whatever it's grouped to |
| `cmd_ungroup_many(player_ids)` | Ungroup multiple players sequentially |
| `cmd_set_members(target, add, remove)` | Full add/remove control |

`cmd_ungroup` handles multiple scenarios:
1. Player has `active_group` → remove from that GROUP player via `cmd_set_members`
2. Player has `synced_to` → remove from parent via `cmd_set_members`
3. Player has `group_members` (is a leader) → remove all members
4. Fallback: scan all dynamic groups for this player and remove

## The Two-Phase `set_members` Pipeline

All grouping commands converge on `cmd_set_members`, which flows through a two-phase pipeline:

```mermaid
flowchart TD
    A[cmd_set_members] --> B[Validate: player available, SET_MEMBERS supported]
    B --> C[Auto-ungroup if parent is already synced]
    C --> D[_handle_set_members]
    D --> E[Handle dissolve if target removed from itself]
    E --> F[Filter additions: availability, can_group_with]
    F --> G[Auto-ungroup children synced elsewhere]
    G --> H[Power on children if needed]
    H --> I{"Parent is GROUP type AND has SET_MEMBERS feature?"}
    I -- Yes --> J[Delegate to player.set_members directly]
    I -- No --> K[_handle_set_members_with_protocols]
    K --> L[Determine parent's active protocol domain]
    L --> M[Translate visible player IDs → protocol player IDs]
    M --> N[Forward protocol members to protocol player's set_members]
    M --> O[Forward native members to parent's set_members]
```

### Phase 1: `_handle_set_members`

Handles validation and common logic for all grouping types:

1. **Dissolve detection**: If the target player is in the removal list, dissolve the entire group (remove all children, then stop)
2. **Compatibility check**: Each child must be in `parent_player.state.can_group_with`
3. **Auto-ungroup**: If a child is synced to a *different* player, ungroup it first
4. **Power management**: Power on children if needed
5. **GROUP type dispatch**: For `PlayerType.GROUP` that also has `PlayerFeature.SET_MEMBERS` in `supported_features`, call `player.set_members()` directly. Static sync groups (which lack this feature) fall through to phase 2 instead.
6. **Regular player dispatch**: For non-GROUP players, proceed to phase 2

### Phase 2: `_handle_set_members_with_protocols`

Bridges the gap between user-visible player IDs and the underlying protocol reality. This is essential because a user might group "Denon AVR" with "HomePod," but the actual sync happens between the Denon's AirPlay protocol player and the HomePod's native AirPlay.

The method:
1. Identifies the parent's active protocol domain and player
2. Translates each visible player ID to the appropriate protocol player ID (or keeps it native)
3. Splits members into protocol-routed and native-routed lists
4. Forwards each list to the appropriate player's `set_members`

This translation is the bridge described in [05-protocol-linking.md](05-protocol-linking.md) — the protocol linking system determines *which* protocol player to use, and this method maps the user's intent onto that protocol reality.

## The Three Relationship Properties

These three properties on `Player` describe group membership from different perspectives. They are frequently confused because they overlap in non-obvious ways.

### `group_members` → Leader/group's view

A list of player IDs that are part of this player's group:

- On a **GROUP** player (sync group, universal group): all member player IDs
- On an **ad-hoc sync leader**: all synced member IDs, including self as first element
- On a **regular player** with no group: empty list

The base implementation uses `_attr_group_members`. Sync groups override it to prefer the sync leader's reported members (source of truth for the actual active group).

### `synced_to` → Child's view

The player ID of the sync leader this player is synced to:

- On a **child** synced to a leader: the leader's player ID
- On a **GROUP** player: always `None` (groups cannot be synced)
- On an **unsynced** player: `None`

The default implementation scans all players from the same provider looking for one whose `group_members` includes this player.

### `active_group` → Any player's view

The player ID of the currently active (playing or paused) GROUP player this player belongs to:

- Computed by scanning all available GROUP players
- Returns the ID of the first GROUP player that is playing/paused and includes this player in its `group_members`
- Protocol players always return `None`

### How They Interact

A player can simultaneously have:
- `synced_to` set (synced to an ad-hoc leader within a sync group)
- `active_group` set (part of a playing GROUP player)

This happens in sync groups: member players are synced to the sync leader (ad-hoc sync at the protocol level), while also being members of the GROUP entity.

```mermaid
graph TD
    subgraph "Sync Group (GROUP entity)"
        SG["SyncGroupPlayer<br/>syncgroup_abc123<br/>group_members: [A, B, C]"]
    end
    subgraph "Protocol-level sync"
        A["Player A (sync leader)<br/>group_members: [A, B, C]"]
        B["Player B<br/>synced_to: A<br/>active_group: syncgroup_abc123"]
        C["Player C<br/>synced_to: A<br/>active_group: syncgroup_abc123"]
    end
    SG -.->|sync_leader| A
    A --> B
    A --> C
```

Player A (sync leader) has `synced_to = None` and `active_group = syncgroup_abc123`.
Players B and C have `synced_to = A` (protocol-level) and `active_group = syncgroup_abc123` (GROUP-level).

## Final Computed Properties

The raw `group_members`, `synced_to`, and `active_group` from providers go through `__final_*` computation in `Player.update_state()` before reaching the API.

### `__final_group_members`

1. If this player has `synced_to` set → return `[]` (children don't have their own group)
2. Translate native `group_members` through `_translate_protocol_ids_to_visible` (maps protocol player IDs to their visible parent players)
3. If an active output protocol exists, include its group members (also translated)
4. For non-GROUP types: ensure self is first; return `[]` if only self

### `__final_synced_to`

1. Check native `synced_to` → translate to `protocol_parent_id` if the sync parent is a protocol player
2. Check linked protocol players' `synced_to` → translate protocol sync parent to visible parent

### `__final_active_group`

1. Protocol players → `None` (follow parent's group state)
2. Scan all enabled, available GROUP players
3. Return the first one that is playing/paused and includes this player in `state.group_members`

## Helper Methods

### `iter_group_members`

Controller method that iterates children of a group/sync leader with filtering:

```python
def iter_group_members(
    self,
    group_player: Player,
    only_powered: bool = False,
    only_playing: bool = False,
    active_only: bool = False,
    exclude_self: bool = True,
) -> Iterator[Player]:
```

Filters: available + enabled (always), powered, playing, active (checks `active_group` matches), exclude self. Used extensively by volume control, announcements, and group commands.

### `_get_player_groups`

Returns all GROUP players a given player belongs to, with optional availability and power filtering. Used to detect group collisions.

### `_get_player_with_redirect`

Redirects playback commands from grouped children to their sync leader or group player:
1. If `synced_to` is set → redirect to sync leader
2. If `active_group` is set → redirect to group player

This ensures commands like play/stop/pause always reach the entity that owns the queue.

## Key Files

| File | Role |
|---|---|
| `music_assistant/providers/sync_group/player.py` | `SyncGroupPlayer` — sync leader delegation, formation/dissolution |
| `music_assistant/providers/sync_group/provider.py` | `SyncGroupProvider` — create/remove/discover |
| `music_assistant/providers/sync_group/constants.py` | `SGP_PREFIX`, `EXTRA_FEATURES_FROM_MEMBERS`, `CONF_MEMBERS_FILTER` |
| `music_assistant/providers/universal_group/player.py` | `UniversalGroupPlayer` — server-side fan-out, power management |
| `music_assistant/providers/universal_group/provider.py` | `UniversalGroupProvider` — create/remove/discover |
| `music_assistant/providers/universal_group/ugp_stream.py` | `UGPStream` — fan-out subscriber model |
| `music_assistant/providers/universal_group/constants.py` | `UGP_PREFIX`, `UGP_FORMAT`, `CONFIG_ENTRY_UGP_NOTE` |
| `music_assistant/controllers/players/controller.py` | `cmd_set_members`, `_handle_set_members`, `_handle_set_members_with_protocols`, `iter_group_members`, `_get_player_groups` |
| `music_assistant/models/player.py` | `group_members`, `synced_to`, `__final_group_members`, `__final_synced_to`, `__final_active_group` |

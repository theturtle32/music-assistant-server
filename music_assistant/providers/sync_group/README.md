# Sync Group Player Provider

## Overview

The Sync Group Player provider enables creating persistent groups of compatible speakers that play audio in perfect synchronization. Unlike temporary sync operations (manually syncing players together), sync groups are permanent player entities with their own queue and configuration.

### Key Features

- **Persistent Groups**: Created groups persist across restarts and appear as regular players
- **Protocol Compatibility**: Automatically enforces that only compatible players (same sync protocol) can be grouped
- **Dynamic Membership**: Optional support for adding/removing members during playback
- **Sync Leader Selection**: Automatically selects and manages the sync leader
- **Queue Ownership**: The sync group owns the playback queue, not individual members

## How It Differs from Manual Sync

| Manual Sync | Sync Group |
|-------------|------------|
| Temporary, dissolves when stopped | Permanent player entity |
| Queue belongs to leader player | Queue belongs to the group |
| Leader is explicitly chosen | Leader is auto-selected |
| Direct player-to-player sync | Abstracted group layer |

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SyncGroupProvider                             │
│  - Discovers/registers sync group players from config           │
│  - Creates/removes sync groups via UI                           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
    ┌─────────▼─────────┐          ┌─────────▼─────────┐
    │  SyncGroupPlayer  │          │  SyncGroupPlayer  │
    │  "Living Room"    │          │  "Whole House"    │
    │                   │          │                   │
    │  sync_leader ─────┼──┐       │  sync_leader ─────┼──┐
    │  group_members:   │  │       │  group_members:   │  │
    │  - AirPlay A      │  │       │  - Sonos 1        │  │
    │  - AirPlay B      │  │       │  - Sonos 2        │  │
    │  - AirPlay C      │  │       │  - Sonos 3        │  │
    └───────────────────┘  │       └───────────────────┘  │
                           │                              │
              ┌────────────▼──────────┐      ┌────────────▼──────────┐
              │   Actual Player A     │      │   Actual Sonos 1      │
              │   (sync leader)       │      │   (sync leader)       │
              │   ┌──synced to it──┐  │      │   ┌──synced to it──┐  │
              │   │ Player B       │  │      │   │ Sonos 2        │  │
              │   │ Player C       │  │      │   │ Sonos 3        │  │
              │   └────────────────┘  │      │   └────────────────┘  │
              └───────────────────────┘      └───────────────────────┘
```

### File Structure

```
sync_group/
├── __init__.py      # Provider setup and config entries
├── provider.py      # SyncGroupProvider - creates/removes groups
├── player.py        # SyncGroupPlayer - group player implementation
├── constants.py     # Constants and feature definitions
├── manifest.json    # Provider manifest (builtin, non-disableable)
└── README.md        # This file
```

## Sync Leader Concept

The sync group doesn't directly play audio. Instead, it delegates to a **sync leader** - one of the member players that actually handles the playback and syncs the other members to itself.

### Sync Leader Selection

The sync leader is selected when the group is formed, which happens when playback starts (or on power-on for groups that have a power control assigned). Selection is also re-evaluated when the current leader is removed from the group or becomes unavailable.

1. **Keep current leader**: If a leader exists and is still available, keep it
2. **Prefer session continuity**: When re-selecting after a leader change while playing, prefer a member that the live session already feeds, since only such a member can inherit the session without a teardown
3. **Prefer protocol continuity**: Otherwise prefer a member that supports the currently active output protocol, so the group at least stays on that protocol
4. **Prioritize static members**: For static groups, prefer members from the configured list
5. **First available**: Otherwise pick the first available member as leader

### Leader Responsibilities

The sync leader is the **source of truth** for the group's playback state:
- Receives the actual `play_media` command
- Syncs all other group members to itself
- Reports playback state, elapsed time, current media, and active source to the group (via the group's `_update_attributes` reading the leader's raw values)
- Contributes features (enqueue, gapless, volume, DSP) to the group

> **State derivation note:** The leader's own `__final_playback_state` does **not** mirror its parent group — that would create a circular dependency (group derives from leader → leader derives from group → both stuck at last value). Members of an active group always report their own raw playback state; only manually-synced clients (`synced_to`) mirror their leader's state.

## Group Types

### Static Groups

- **Fixed membership**: Members defined at creation, cannot be changed during playback
- **Use case**: Permanent whole-home audio setup
- **Behavior**: All static members rejoin automatically when playback starts

### Dynamic Groups

- **Flexible membership**: Members can be added/removed at any time
- **Use case**: Ad-hoc grouping based on current needs
- **Behavior**: Supports `SET_MEMBERS` feature for runtime changes
- **Configuration**: Enable "Dynamic members" option when creating the group

## Protocol Compatibility

Players can only be grouped if they support the same sync protocol. This is enforced through the `can_group_with` mechanism:

1. **First member added**: Its `can_group_with` set becomes the reference
2. **Subsequent members**: Must be in the reference set to be added
3. **Incompatible players**: Silently skipped during group formation

### Compatible Protocol Examples

- AirPlay players can group with other AirPlay players
- Sonos players can group with other Sonos players
- Squeezelite players can group with other Squeezelite players
- **Cross-protocol grouping is NOT supported**

## Protocol Linking Integration

The sync group leverages the Player Controller's protocol linking system through its elected sync leader. This is important for devices that support multiple streaming protocols.

### How It Works

When a sync group starts playback:

1. **Sync leader is elected** from the group members
2. **Play command forwarded** to the sync leader via `_handle_play_media()`
3. **Protocol selection happens** on the sync leader using `_select_best_output_protocol()`
4. **Best protocol chosen** based on:
   - Protocol already grouped/synced with other players (highest priority)
   - User's preferred output protocol setting
   - Native playback if available
   - Best available protocol by priority

### Example Scenario

Consider a sync group mixing a Universal Player (Denon AVR with multiple protocols) and native AirPlay devices:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Sync Group: "Living Room"                     │
│                                                                  │
│  Members: Denon AVR, HomePod, Apple TV                          │
│  Sync Leader: Denon AVR (Universal Player)                       │
│  Compatible via: AirPlay protocol                                │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ play_media() forwarded to leader
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Denon AVR (Sync Leader - Universal Player)          │
│                                                                  │
│  Linked Output Protocols:                                        │
│  - AirPlay  ◄── selected (members are AirPlay-compatible)        │
│  - Chromecast                                                    │
│  - DLNA                                                          │
│                                                                  │
│  → _select_best_output_protocol() chooses AirPlay                │
│  → Syncs HomePod and Apple TV via AirPlay protocol               │
└─────────────────────────────────────────────────────────────────┘
```

In this scenario, the Denon AVR has three output protocols available. Since the other sync group members (HomePod, Apple TV) are AirPlay devices, the protocol selection logic picks AirPlay as the output protocol. All three devices then sync together via AirPlay.

### Why This Matters

- **Unified experience**: Users interact with one sync group player
- **Automatic optimization**: The leader picks the best protocol for its device type
- **Protocol-aware syncing**: Members sync using their native protocol (Sonos-to-Sonos, AirPlay-to-AirPlay)
- **Fallback support**: If native protocol unavailable, linked protocols provide alternatives

For detailed information on protocol linking, output protocol selection, and how devices with multiple protocols are handled, see the [Player Controller README](../../controllers/players/README.md#multi-protocol-player-system).

## Group Lifecycle

The group's lifecycle is driven by the **playback session**, not by power:

- Playback **forms** the group: both `play_media()` and `play()` call `_form_syncgroup()`, which selects a sync leader and syncs all members to it
- `stop()` **dissolves** the group immediately, releasing the members back to individual control
- A **natural** transition to IDLE (the queue simply ran out) starts a grace timer and dissolves the group after `IDLE_GRACE_SECONDS` (10 seconds), so an end-of-track gap or a quick "play something else" doesn't tear down the live sync session
- Removing the sync leader from a playing group schedules a debounced re-form after `REFORM_DEBOUNCE_SECONDS` (2 seconds), so cascaded unjoins coalesce into a single restart

While the group is dormant it does **not** capture its members: they remain individually controllable and a command targeting a member is not redirected to the group.

### Session State

`is_active_session` — not `powered` — is the canonical "this group is holding its members" signal. It is True while a sync leader is set, while the idle grace timer is pending, or while a debounced re-form is pending. The base `Player` model's active-group derivation consults it to decide whether the configured members should report this group as their `active_group`.

### Optional Power Control

`PlayerFeature.POWER` is deliberately **not** advertised by default. Users who want an explicit on/off toggle can assign **Fake power control** to the group; the feature is then advertised and:

- `power(True)` re-applies the configured preset members and pre-forms the group, capturing its members immediately
- `power(False)` stops any playback and dissolves the group
- while powered on, `stop()` and the idle grace timer leave the group formed — it stays pinned as active until the user powers it off

### Forming

```
1. play_media(media) / play()   (or cmd_power(syncgroup, True) with fake power control)
   │
2. _form_syncgroup() runs
   │
   ├─► Cancel any pending idle-grace or re-form timer
   ├─► Select sync leader (if not already set)
   ├─► Move sync leader to the front of the member list
   ├─► If the leader still reports synced_to, wait for it to settle (abort if stuck)
   ├─► If leader is currently playing something else, stop it (and wait for IDLE)
   └─► _handle_set_members on the leader to sync the remaining members
```

### Starting Playback

```
1. User starts playback on SyncGroupPlayer
   │
2. play_media(media)
   │
   ├─► Optimistically set _attr_current_media / _attr_active_source
   ├─► _form_syncgroup()            # idempotent - no-op when already formed
   └─► _handle_play_media(sync_leader, media)   # leader actually plays
   │
3. Leader starts playback, synced members follow
```

### Stopping Playback

```
1. User stops playback on SyncGroupPlayer
   │
2. stop()
   │
   ├─► Cancel any pending idle-grace / re-form timer
   ├─► Forward the stop to the sync leader
   └─► _dissolve_syncgroup()   # skipped when pinned via fake power control
```

### Dissolving

```
_dissolve_syncgroup()
   │
   ├─► _handle_set_members on leader to remove all sync children (waits for state)
   ├─► Schedule a clear of the leader's active_output_protocol (deferred until it reports IDLE)
   └─► sync_leader = None
   │
state event emitted
```

### State Polling

While the group is playing, `SyncGroupPlayer.poll()` is called every 1 second to refresh `elapsed_time` from the sync leader. When idle, the poll interval drops to 30 seconds. This avoids the per-second eventbus cascade that would happen if we forwarded every elapsed_time tick from the leader through the group's update chain.

## Dynamic Member Management

When `SET_MEMBERS` is called on a dynamic group:

### Adding Members

1. Validate the member exists, is available, and is permitted by the configured allowed-members list (`allowed_members`, empty means "any player may join"; preset members always may)
2. If there is no sync leader yet (empty / dormant group): just register the member; sync happens when the group is next formed
3. Otherwise check compatibility with the current sync leader's `can_group_with` (which already includes all of the leader's linked output protocols, so e.g. an AirPlay-only player IS valid for a Sonos leader that has AirPlay as a linked protocol)
4. Incompatible members are **not** registered (avoids stranding orphan entries in the group)
5. Compatible members are appended to the internal member list and forwarded to `cmd_set_members` on the leader, which handles protocol selection (and possibly switching the leader to a different output protocol so the new member can be grouped via that protocol)

### Removing Members

1. Remove from the internal member list (static members cannot be removed)
2. If removing the **sync leader** while playing:
   - If the active protocol supports dynamic leader switching (provider domain is in `PROVIDERS_WITH_DYNAMIC_LEADER_SWITCH` — currently AirPlay, Snapcast, Sendspin), perform a **seamless handoff** at the protocol level: pick a new leader from the live session, then call `set_members(player_ids_to_remove=[old_leader_protocol])` on the old session player and `set_members(player_ids_to_add=[remaining_protocol_ids])` on the new leader's protocol player. Remaining members keep playing.
   - If no remaining member is part of the live session (e.g. only freshly-added players are left), or the protocol doesn't support handoff: fall back to **dissolve + re-form** (brief audio gap)
3. If removing a non-leader member: forward to `cmd_set_members` on the leader

### Removing Last Member

If the last member is removed, the group is dissolved (leader stopped, sync_leader cleared).

## Feature Inheritance

The SyncGroupPlayer has limited base features but inherits additional capabilities from the sync leader:

### Base Features
- `PLAY_MEDIA` - Always supported
- `POWER` - Only when the user assigned 'Fake power control' to the group

### Features from Sync Leader (when active)
- `ENQUEUE` - Queue next track
- `GAPLESS_PLAYBACK` - Seamless track transitions
- `VOLUME_SET` - Volume control
- `VOLUME_MUTE` - Mute control
- `MULTI_DEVICE_DSP` - DSP processing

When there is no sync leader yet, these features are derived from all available (configured) members instead, so controls like volume are advertised while the group is dormant.

### Dynamic Feature
- `SET_MEMBERS` - Only if group is configured as dynamic

## Configuration Options

### Group Members

Multi-select list of players to include in the group. Only non-group players are shown as options. For static groups, these are the permanent members. For dynamic groups, these are the initial members.

### Enable Dynamic Members

Boolean option to allow runtime member changes. When enabled:
- Group supports `SET_MEMBERS` feature
- Members can be added/removed via UI or API
- Group can start with zero members

### Allowed Members

Advanced option (only relevant for dynamic groups) that restricts which players may join at runtime. When left empty, any compatible player may join. Players in the Group Members preset are always allowed.

## Provider Details

### Player ID Format

Sync group players use the format: `syncgroup_{random_8_chars}`

Example: `syncgroup_ab12cd34`

### Provider Features

- `CREATE_GROUP_PLAYER` - Create new sync groups
- `REMOVE_GROUP_PLAYER` - Delete sync groups

### Builtin Provider

The Sync Group provider is:
- **Builtin**: Automatically available, no installation needed
- **Single instance**: Only one provider instance exists
- **Non-disableable**: Cannot be disabled by users

## State Properties

The SyncGroupPlayer reads most state from the sync leader's **raw** attributes (deliberately not `.state.*`, see the leader-responsibilities note above):

| Property | Source |
|----------|--------|
| `powered` | `_attr_powered` — `None` unless a power control is assigned, in which case `power()` sets it. Session capture is tracked by `is_active_session`, not by this attribute |
| `playback_state` | Sync leader's raw `state.playback_state` (or IDLE if no leader) |
| `elapsed_time` | Sync leader's raw `state.elapsed_time` |
| `elapsed_time_last_updated` | Sync leader's raw `state.elapsed_time_last_updated` |
| `current_media` | Sync leader's raw `current_media` (set optimistically in `play_media`) |
| `active_source` | Sync leader's raw `active_source` (set optimistically in `play_media`) |
| `group_members` | Sync leader's reported `state.group_members` (preferred) or internal list |
| `can_group_with` | Static groups: the configured member list. Dynamic groups: aggregated from all current members' `can_group_with` |
| `supported_features` | Base features + features inherited from the active sync leader (or from the available members while dormant) |

## Related Documentation

- [Player Controller README](../../controllers/players/README.md) - For understanding player management, protocol linking, and sync coordination
- [Universal Player README](../universal_player/README.md) - For understanding how protocol players are merged

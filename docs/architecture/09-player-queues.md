# 09 — Player Queue Management

The Player Queue system sits between the media library and the audio streaming pipeline. Every player in Music Assistant has an associated `PlayerQueue` that holds the ordered list of items to play, manages playback state, and orchestrates the handoff between tracks. The `PlayerQueuesController` is the central coordinator — it resolves media into queue items, drives playback via the player controller, and pre-warms audio buffers to ensure seamless transitions.

## Architecture Overview

```mermaid
graph LR
    subgraph "Entry Points"
        API["play_media()<br/>play_index()<br/>next() / previous()"]
    end

    subgraph "PlayerQueuesController"
        PQ[Queue State<br/>_queues · _queue_items]
        Load[load() — insert/shuffle]
        PI[play_index() — playback flow]
        LI[_load_item() — stream details + buffer]
        PNA[_prepare_next_audio_buffer()]
        LNQ[load_next_queue_item()]
    end

    subgraph "Player Layer"
        PC[PlayerController<br/>play_media · cmd_stop · cmd_pause]
    end

    subgraph "Streams Layer"
        SA[StreamsAudio<br/>get_stream_details]
        AB[AudioBuffer<br/>get_buffer · fill]
    end

    API --> PQ
    PQ --> Load --> PI
    PI --> LI
    LI --> SA
    LI --> AB
    PI --> PC
    PNA --> AB
    LNQ --> LI
```

## PlayerQueuesController

`PlayerQueuesController` extends `CoreController` with `domain = "player_queues"`. It manages two in-memory dictionaries that hold all runtime state:

| Dictionary | Key | Value |
|-----------|-----|-------|
| `_queues` | `queue_id` (= player_id) | `PlayerQueue` — playback state, indices, flags |
| `_queue_items` | `queue_id` | `list[QueueItem]` — the ordered playlist |

Additional state:
- `_prev_states` — previous `CompareState` per queue (for change detection in update signals)
- `_transitioning_players` — set of player IDs currently between tracks (prevents duplicate advance commands)
- `_play_action_locks` — per-queue `asyncio.Lock` for serializing play-related operations

### The `@handle_play_action` Decorator

Play-related methods (`play_media`, `play_index`) are wrapped with `@handle_play_action`, which:
1. If already inside a play action (`IN_PLAY_ACTION` ContextVar is set), skip lock acquisition (nested call)
2. Otherwise, acquire the per-queue lock with a **60-second timeout** (`PLAY_ACTION_LOCK_TIMEOUT`). If the timeout expires, the stuck lock is force-replaced with a fresh one to recover the queue.
3. Sets `ATTR_PLAY_ACTION_IN_PROGRESS` on the queue
4. Sets the `IN_PLAY_ACTION` `ContextVar` for nested calls
5. Ensures cleanup on exit

This prevents concurrent play commands from racing each other on the same queue, with the timeout ensuring a stuck lock never permanently blocks a queue.

## PlayerQueue Dataclass

`PlayerQueue` (from `music_assistant_models.player_queue`) holds the runtime state of a single queue:

| Field | Type | Description |
|-------|------|-------------|
| `queue_id` | `str` | Same as the player ID |
| `display_name` | `str` | Human-readable name |
| `active` | `bool` | Whether this queue is the player's active source |
| `available` | `bool` | Whether the associated player is available |
| `state` | `PlaybackState` | IDLE, PLAYING, PAUSED |
| `shuffle_enabled` | `bool` | Shuffle mode |
| `repeat_mode` | `RepeatMode` | OFF, ONE, ALL |
| `dont_stop_the_music_enabled` | `bool` | Auto-radio when queue runs out |
| `current_index` | `int` | Index of the currently playing item |
| `index_in_buffer` | `int` | Index of the item currently in the audio buffer |
| `elapsed_time` | `float` | Seconds elapsed in current track |
| `elapsed_time_last_updated` | `float` | Timestamp of last elapsed_time update |
| `current_item` | `QueueItem \| None` | The item currently playing |
| `next_item` | `QueueItem \| None` | The next item (for UI display) |
| `resume_pos` | `float` | Position to resume from after pause |
| `flow_mode` | `bool` | Whether flow mode is active (set by streams layer) |
| `flow_mode_stream_log` | `list` | Items played during the current flow stream |
| `radio_source` | `list` | Seed items for radio mode |
| `enqueued_media_items` | `list` | Original media items that were enqueued |
| `session_id` | `str` | Current playback session (validated in stream URLs) |
| `items` | `int` | Total item count |
| `userid` | `str \| None` | User who initiated playback |

The `corrected_elapsed_time` property accounts for wall-clock drift while the state is PLAYING.

## QueueItem Dataclass

`QueueItem` (from `music_assistant_models.queue_item`) represents a single entry in the queue:

| Field | Type | Description |
|-------|------|-------------|
| `queue_id` | `str` | Parent queue ID |
| `queue_item_id` | `str` | Unique ID for this queue entry |
| `name` | `str` | Display name |
| `duration` | `float` | Track duration in seconds |
| `sort_index` | `int` | Original insertion order (for un-shuffle) |
| `streamdetails` | `StreamDetails \| None` | Filled when playback starts |
| `media_item` | `MediaItemType \| None` | The resolved media item |
| `image` | `MediaItemImage \| None` | Cover art |
| `index` | `int` | Current position in queue |
| `available` | `bool` | Whether the item can be played |
| `extra_attributes` | `dict` | Provider-specific metadata |

The `uri` and `media_type` properties are derived from `media_item`.

## Playing Media

### `play_media` — The Main Entry Point

`play_media(queue_id, media, option, radio_mode, start_item, username)` is the primary API for initiating playback. It accepts flexible input:

- **`str`** — parsed as a URI via `mass.music.get_item_by_uri()`
- **`ItemMapping`** — a lightweight reference to a media item
- **`MediaItemType`** — a fully resolved media item
- **`list`** — any combination of the above

The `QueueOption` enum controls how items are inserted:

| Option | Behavior |
|--------|----------|
| `REPLACE` | Clear queue, load items, start playback from index 0 |
| `PLAY` | Insert at current position, start playing the first new item |
| `NEXT` | Insert after the current item |
| `REPLACE_NEXT` | Replace everything after current item |
| `ADD` | Append to the end (or after current if shuffled) |

If `option` is `None`, it defaults to a per-media-type config value (`default_enqueue_option_{media_type}`).

### Radio Mode

When `radio_mode=True`, `play_media` replaces the resolved items with a mix of similar tracks:

1. `_get_radio_tracks(is_initial_radio_mode=True)` samples base tracks from each seed item's `radio_mode_base_tracks()` on the music provider.
2. Fetches similar tracks via `TracksController.similar_tracks()`.
3. Filters out tracks longer than `RADIO_TRACK_MAX_DURATION_SECS` (20 minutes) and already-queued tracks.
4. The `radio_source` on the queue is set so the system can refill when the queue runs low.

Radio refill is triggered in `_update_queue_from_player` when fewer than 5 tracks remain after the current index.

### "Don't Stop the Music"

`dont_stop_the_music_enabled` is a gentler version of radio mode — when the queue is about to run out, it uses the originally `enqueued_media_items` as seed and calls `_fill_radio_tracks` to append similar content.

## Playback Flow

### `play_index` — Starting a Track

`play_index(queue_id, index, seek_position, fade_in)` is the core playback driver. For podcast episodes and audiobooks, if no explicit `seek_position` is provided, the resume position is restored from `resume_position_ms`. On failure (`MediaNotFoundError` or `AudioError`), the item is marked unavailable and the queue advances to the next index with `allow_repeat=False` (preventing infinite loops even with repeat-all enabled):

```mermaid
sequenceDiagram
    participant PQ as PlayerQueuesController
    participant LI as _load_item
    participant SA as StreamsAudio
    participant AB as AudioBuffer
    participant PC as PlayerController

    PQ->>PQ: Add queue_id to _transitioning_players
    PQ->>PQ: New session_id, update index_in_buffer

    loop Up to 5 retries on MediaNotFoundError
        PQ->>LI: _load_item(queue_item, is_start=True)
        LI->>SA: get_stream_details(queue_item)
        SA-->>LI: StreamDetails
        LI->>AB: AudioBuffer.get_buffer(wait_ready=True)
        AB-->>LI: Buffer ready
    end

    PQ->>PQ: player_media_from_queue_item()
    PQ->>PC: play_media(player_id, PlayerMedia)
    PQ->>PQ: Update current_index, current_item
    PQ->>PQ: signal_update()
    PQ->>PQ: Remove from _transitioning_players
```

Key details:

1. **Retry loop** — if `_load_item` raises `MediaNotFoundError` or `AudioError`, the item is marked unavailable and the next index is tried (up to 5 attempts).
2. **`_load_item`** fills `queue_item.streamdetails` via `StreamsAudio.get_stream_details()` and, when `is_start=True`, eagerly creates an `AudioBuffer` with `wait_ready=True` so the player can start immediately.
3. **Dispatch** — calls `PlayerController.play_media()` (not `cmd_play`, which is the resume path) with a `PlayerMedia` object containing the stream URL, format, and queue context.
4. **Session ID** — a new `shortuuid` is generated for each `play_index` call. Stream URLs embed this session ID; the streams controller validates it to reject stale requests.

### `_load_item` — Preparing Stream Details

`_load_item` is responsible for making a queue item playable:

1. Checks `queue_item.available` — raises `MediaNotFoundError` if false.
2. For tracks, prefers the library version over the provider version (richer metadata). Special-cases YTM and album image precedence.
3. Determines album-context loudness (tracks from the same album can share loudness measurements).
4. Calls `StreamsAudio.get_stream_details()` to resolve the actual audio source, format, loudness data, and normalization mode.
5. When `is_start=True`, calls `AudioBuffer.get_buffer(wait_ready=True, reason="prepare")` to pre-fill the buffer before the player asks for the stream.

### Pre-Warming the Next Track

Seamless transitions require the next track's buffer to be ready before the current track ends. Two mechanisms coordinate this:

**1. Buffer pre-warm (~60s before end)**

During PCM streaming in `get_queue_item_stream`, when the consumed position passes `duration - 60` seconds, the streams audio layer calls `_prepare_next_audio_buffer()`:

```python
def _prepare_next_audio_buffer(self, queue_id: str) -> None:
    # Async task: fetch stream details for next_item,
    # then AudioBuffer.get_buffer(wait_ready=True, reason="prepare_next")
    self.mass.create_task(_do_prepare)
```

**2. Preloading stream details and enqueuing**

After a track is loaded into the buffer (`track_loaded_in_buffer`), `_preload_next_item` waits until that item becomes the `current_item` (with a 120-second timeout to guard against race conditions), then calls `load_next_queue_item()` to resolve the next item's stream details. It then schedules `_enqueue_next_item()`, which calls `PlayerController.enqueue_next_media()` to tell the player about the upcoming track.

**3. Flow stream recovery**

After a flow stream finishes, `queue_buffer_completed` polls for up to 60 seconds waiting for the player to go idle. If the original session is still active and new items have been appended to the queue, it calls `play_index` to resume playback automatically.

### `load_next_queue_item` — Advancing the Queue

Called by the streams layer when the current stream is about to end (crossfade transitions, flow mode loop), and by the preload path. It:

1. Finds the next valid index via `_get_next_index()` (respecting repeat mode).
2. Calls `_load_item()` (without `is_start`, so no buffer warm here — that's handled separately by `_prepare_next_audio_buffer`).
3. Returns the resolved `QueueItem` or raises `QueueEmpty`.
4. Retries up to 10 times if items are unavailable, skipping them.

## Queue Loading and Shuffle

### `load` — Inserting Items

`load(queue_id, queue_items, insert_at_index, keep_remaining, keep_played, shuffle)` is the low-level method for modifying the queue contents:

- `keep_played=False` drops items before `insert_at_index` (REPLACE semantics).
- `keep_remaining=True` preserves items after `insert_at_index` (ADD/NEXT semantics).
- Each item's `sort_index` is set to its original insertion order (for un-shuffle).
- If `shuffle=True`, `_smart_shuffle` randomizes the new portion while trying to avoid adjacent duplicate track names.

### Shuffle and Repeat

**Shuffle:**
- `set_shuffle(enabled)` rebuilds the queue tail. When enabled, it calls `load` with `shuffle=True` on all items after the current index. When disabled, it restores `sort_index` order.
- Radio mode bypasses shuffle (radio ordering is intentional).

**Repeat modes** affect `_get_next_index`:

| Mode | At last item | During skip (`next()`) |
|------|-------------|------------------------|
| `OFF` | Returns `None` (queue ends) | Normal advance |
| `ONE` | Same index (loop single track) | Advances normally (skip overrides repeat-one) |
| `ALL` | Returns index 0 (loop entire queue) | Normal advance |

## Playback Controls

| Method | Behavior |
|--------|----------|
| `play()` | If queue is active and PAUSED, resumes via `queue_player.play()`; otherwise falls through to `resume()` |
| `pause()` | Saves `resume_pos`, sends `cmd_pause` to player; starts `_watch_pause` (auto-stop after ~30s paused) |
| `resume()` | Computes position from `resume_pos` / `corrected_elapsed_time`; optional fade-in if idle > 60s; radio forces position 0; calls `play_index()` |
| `stop()` | Sends `cmd_stop` to player; clears transitioning state; schedules buffer cleanup |
| `next()` | Adds to `_transitioning_players`; updates UI index; debounced `play_index` after 1s |
| `previous()` | If elapsed < 5s, go to previous index; otherwise restart current track; debounced `play_index` |
| `seek(position)` | Calls `play_index(queue_id, current_index, seek_position=position)` |
| `play_pause()` | Toggle between `play()` and `pause()` |

### The `IN_QUEUE_COMMAND` Guard

Player commands like `cmd_stop` and `cmd_pause` on the `PlayerController` check whether the player has an active queue. If so, they redirect to `player_queues.stop()` / `player_queues.pause()`. But queue methods themselves need to call those same `cmd_*` methods without triggering the redirect.

The `IN_QUEUE_COMMAND` `ContextVar` (defined on `PlayerController`) breaks this cycle:

```python
# PlayerController checks:
if not IN_QUEUE_COMMAND.get() and active_queue:
    return await self.mass.player_queues.stop(queue_id)

# Queue methods set it before calling player commands:
IN_QUEUE_COMMAND.set(True)
await self.mass.players.cmd_stop(player_id)
```

## Transition Guard

`_transitioning_players` is a set of player IDs currently between tracks. It is:
- **Set** in `next()`, `previous()`, and at the start of `play_index()`
- **Cleared** in `play_index()`'s `finally` block

When `on_player_update` fires for a transitioning player, the handler returns early. This prevents transient player state during track changes from fighting the queue's intended state.

## Playback Progress Reporting

`_update_queue_from_player` calls `_handle_playback_progress_report` on three triggers: when `state` changes, when `current_item_id` changes, or on the 30-second cadence (`PLAYBACK_REPORT_INTERVAL_SECONDS`). The report emits an `EventType.MEDIA_ITEM_PLAYED` event carrying a `MediaItemPlaybackProgressReport` that includes:

- URI, media type, name, artists, album
- Duration, `seconds_played`, `fully_played`
- `is_playing`, `userid`

This event drives scrobbling (Last.fm, ListenBrainz) and playlog updates.

## Queue Resolution: `get_active_queue`

When a command or stream request needs the active queue for a player, `PlayerController.get_active_queue(player)` resolves it through a 4-step chain:

1. **Sync leader** — if `player.state.synced_to` points to another player, recurse into that player's queue.
2. **Active GROUP** — if `player.state.active_group` points to a group player, recurse into the group player's queue.
3. **Active source / player ID** — look up `player.state.active_source` (or fall back to `player.player_id`) as a queue ID.
4. **Protocol parent** — if the player is `PlayerType.PROTOCOL` with a `protocol_parent_id`, recurse into the parent player's queue.

This resolution chain ensures that grouped players, sync children, and protocol wrappers all find the correct queue — the one owned by their effective leader or parent. It is used throughout the streaming pipeline (e.g., `_prepare_next_audio_buffer` pre-warms based on the resolved queue, not the individual player's naive queue).

## Queue as Active Source

The queue is the "usual active source" for a player, but not the only possibility. On every player update, the queue checks:

```python
queue.active = player.state.active_source in (queue.queue_id, None)
```

When `active_source` is another ID (e.g. a plugin source like Spotify Connect), the queue becomes inactive. If this is the first update for this queue (no entry in `_prev_states`), its state is set to IDLE and processing returns early. Otherwise, the queue falls through to normal `_update_queue_from_player` processing. Plugin sources can handle their own `next_track`, `previous_track`, `seek`, and `volume` commands — the `PlayerController` checks for an active plugin source before routing to the queue (see [04-player-controller.md](04-player-controller.md) and [11-plugin-system.md](11-plugin-system.md) for the full plugin source architecture).

## Queue Events

| Event | When |
|-------|------|
| `QUEUE_ADDED` | First player update after registration |
| `QUEUE_UPDATED` | Any queue state change (`signal_update`) |
| `QUEUE_ITEMS_UPDATED` | Queue contents changed (`signal_update` with `items_changed=True`) |
| `QUEUE_TIME_UPDATED` | Elapsed-time-only changes (> 2s delta) or explicit time corrections |
| `MEDIA_ITEM_PLAYED` | Progress reporting / scrobbling every 30s |

See [01-event-system.md](01-event-system.md) for the general event infrastructure.

## Key Files

| File | Role |
|------|------|
| `controllers/player_queues.py` | PlayerQueuesController — queue management and playback orchestration |
| `music_assistant_models/player_queue.py` | PlayerQueue dataclass (in models package) |
| `music_assistant_models/queue_item.py` | QueueItem dataclass (in models package) |
| `controllers/players/controller.py` | PlayerController — receives play/stop/pause commands from the queue |
| `controllers/streams/audio.py` | StreamsAudio — provides `get_stream_details` and buffer management |
| `controllers/streams/audio_buffer.py` | AudioBuffer — pre-filled PCM buffer |
| `constants.py` | `PLAYBACK_REPORT_INTERVAL_SECONDS`, `QueueOption`, config keys |

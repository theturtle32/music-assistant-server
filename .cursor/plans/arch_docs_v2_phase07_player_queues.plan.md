---
name: arch_docs_v2_phase07_player_queues
overview: "Phase 7. Rewrite most of 09-player-queues.md: the monolith became a 14-module mixin package, server-side state moved to PlayerQueueData, radio mode was replaced by dynamic playlists over a bounded ManagedPool, 'don't stop the music' became configurable Autoplay, and shuffle gained a recency-tiered smart mode."
todos:
  - id: preflight
    content: "Pre-flight: verify the package module map, PlayerQueueData field split, managed pool, autoplay, and smart shuffle against the working tree"
    status: completed
  - id: structure
    content: "09-player-queues.md: replace the controller architecture section with the package + mixin overview and a PlayerQueue vs PlayerQueueData split; link to the in-tree README for the module table"
    status: completed
  - id: fields
    content: "09-player-queues.md: rebuild the PlayerQueue and QueueItem field tables field by field"
    status: completed
  - id: locking
    content: "09-player-queues.md: correct the handle_play_action decorator (helpers.py, wrapped methods, PlayerQueueData.play_action_refcount)"
    status: completed
  - id: dynamic
    content: "09-player-queues.md: replace the Radio Mode and Dynamic Playlists sections with the ManagedPool / is_dynamic model"
    status: completed
  - id: autoplay
    content: "09-player-queues.md: replace 'Don't Stop the Music' with the Autoplay modes section"
    status: completed
  - id: shuffle
    content: "09-player-queues.md: rewrite shuffle for SmartShuffle recency tiers and dynamic-mode forcing"
    status: completed
  - id: playback
    content: "09-player-queues.md: refresh play_media / play_index / _load_item / pre-warm sections including the renamed prepare_next_audio_buffer"
    status: completed
  - id: persistence
    content: "09-player-queues.md: rewrite queue restore for PlayerQueueData.from_cache and the versioned two-category cache"
    status: completed
  - id: perqueue
    content: "09-player-queues.md: add a per-queue configuration section and cross-link 02-configuration.md"
    status: completed
  - id: streams_boundary
    content: "10-streaming-pipeline.md: patch the queue boundary (session_id on PlayerQueueData, flow session validation, prepare_next_audio_buffer)"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: in_progress
isProject: false
---

# Phase 7 — Player queues

File: `docs/architecture/09-player-queues.md` (60–70% rewrite), plus a small targeted patch to
`docs/architecture/10-streaming-pipeline.md`.

Related in-tree README: `music_assistant/controllers/player_queues/README.md`, which upstream
keeps current and which already covers the module layout, config inventory, and mixin boundaries.
**Link to it rather than reproducing those tables.** Our doc should own cross-stack integration
(players, streams, events, API), end-to-end flows, and what changed since the monolith.

## Structure

`controllers/player_queues.py` (~3300 lines) is now `controllers/player_queues/` with `base.py`,
`config.py`, `constants.py`, `controller.py`, `helpers.py`, `autoplay.py`, `managed_pool.py`,
`media_resolver.py`, `playback_tracker.py`, `queue_loader.py`, `smart_shuffle.py`, `state.py`,
`stream_feeder.py`, and `README.md` (#4263, #4509).

The most important conceptual addition: **`PlayerQueue` (wire model) vs `PlayerQueueData`
(server-side state)**. The doc's parallel dicts (`_queues`, `_queue_items`, `_prev_states`,
`_transitioning_players`, `_play_action_refcount`) are replaced by a single
`_queue_data: dict[str, PlayerQueueData]`. Server-only fields living on `PlayerQueueData`:
`items`, `source_items`, `enqueued_media_items`, `userid`, `session_id`,
`flow_mode_stream_log`, `flow_buffer_completed`, `next_item_id_enqueued`, `transitioning`,
`play_action_refcount`.

## Field tables

Verify field by field. Known deltas:

- `dont_stop_the_music_enabled` → **`autoplay_enabled`** (legacy key mirrored on serialize only).
- `radio_source: list[MediaItemType]` → **`sources: list[ItemMapping]`** (wire projection; full
  items in `PlayerQueueData.source_items`).
- Moved to `PlayerQueueData`: `flow_mode_stream_log`, `next_item_id_enqueued`, `session_id`,
  `userid`, `enqueued_media_items`.
- **Removed:** `items_last_updated` (added in round 1 — remove it again).
- **Missing:** `crossfade_enabled`, `overlay_enabled`, `overlay_source`, `overlay_volume`,
  `smart_fades_active`, `smart_shuffle_active`, `playback_speed`, `is_dynamic`.
- `corrected_elapsed_time` must account for `playback_speed` when PLAYING.
- `QueueItem.duration` is `int | None`, not `float`; `media_item` is
  `PlayableMediaItemType | None`. Items are slimmed at enqueue by `build_queue_item` to cut memory
  on large queues (#4697).

Pin the models version the field tables were verified against (`music-assistant-models`, currently
1.1.173) so a future reader knows what to re-check.

## Locking

`handle_play_action` lives in `helpers.py` and wraps `_handle_play_media` (in `queue_loader.py`),
`play_index`, `stop`, `next`, `previous`, `resume`, and `_handle_play`. The refcount is
`PlayerQueueData.play_action_refcount`. Public `play_media()` delegates to the decorated
`_handle_play_media()`. When the refcount drops to zero the decorator calls
`on_player_update(player, {})` before clearing the flag. The transition guard is per-queue
(`PlayerQueueData.transitioning` via `_set_transitioning()`), not a controller-level set.

## Radio mode → dynamic playlists

This replaces two doc sections. `radio_mode` is **deprecated**: it is translated to
`radio_playlist://` dynamic-playlist URIs with a warning. `_fill_radio_tracks`,
`RADIO_TRACK_MAX_DURATION_SECS`, and the `radio_mode_base_tracks()` abstract method no longer
exist.

The dynamic model: a dynamic playlist is a **source**, not an upfront batch. The queue enters
`_enter_dynamic_mode`, which drops the upcoming tail and has `ManagedPool.fill()` build a bounded
mix (target 25, max 50), weighted and recency-gated. Finite sources play through once (#4503).
Refill goes through `_fill_dynamic_tracks`. ADD/NEXT onto an active dynamic queue adds finite items
as **sources** rather than expanded tracks (#4521). Shuffle and repeat are locked in dynamic mode —
dynamic mode forces `shuffle_enabled=True` and rejects manual toggling.

Driving PRs: #4498, #4479, #4513, #4522–#4528.

## Autoplay

`dont_stop_the_music_enabled` became `autoplay_enabled` (#4404), and refill is handled by the
`Autoplay` helper with `AUTO` / `SIMILAR` / `LIBRARY` / `PLAYLIST` modes (#4446) via
`_fill_autoplay_tracks`, recency-gated with `gate_tracks`. The API alias
`player_queues/dont_stop_the_music` remains. Autoplay does **not** run when `is_dynamic` — the
managed pool owns that path.

## Smart shuffle

`SmartShuffle` (`smart_shuffle.py`) uses recency tiers (song and artist windows plus a duplicate
gap) sourced from the shared `RecencyEngine` (Phase 10 documents the engine), then interleaves with
artist spacing (#4475, #4773). Plain shuffle is `random.sample`. There is a per-queue
`smart_shuffle_enabled` with a global default (#4537) and a derived `smart_shuffle_active` flag on
the wire model. The doc's claim that `_smart_shuffle` merely avoids adjacent duplicate track names
is obsolete.

## Playback flow

- `play_media` gained `start_from_beginning` (podcasts) and `sort_by`; radio and `AudioSource`
  share `default_enqueue_option_live_sources`.
- `play_index` calls `audio_processing.start_session()`, holds the play action until the player
  reports PLAYING (`PLAYBACK_START_TIMEOUT`), resets `elapsed_time` on item switch (#4898), and
  keeps items available on `AudioError` — only `MediaNotFoundError` marks an item unavailable.
- `_load_item` moved to `queue_loader.py`, bypasses `AudioBuffer` for `MediaType.AUDIO_SOURCE`,
  uses `BYPASS_THROTTLER`, and enriches library metadata when an item becomes current or next.
- Pre-warm: `_prepare_next_audio_buffer()` is now the public `prepare_next_audio_buffer()` in
  `stream_feeder.py`. The preload wait is `max(120, int(duration) + 10)` one-second polls.
  `_enqueue_next_item` waits for PLAYING and re-validates `session_id` before enqueueing (#4906).
- `load_next_queue_item` carries `playback_speed` forward across consecutive audiobook/podcast
  episodes.
- Also cover `MediaResolver` (artist/album/playlist → tracks) and
  `flow_stream_finished()` / `queue_buffer_completed` for flow EOF without idle (#4406).

## Persistence and restore

Queues now survive restarts (#4529). Restore is
`PlayerQueueData.from_cache(state_data, items_data)` with a versioned envelope
(`cache_format_version`), resilient deserialization of `sources` / `source_items` /
`enqueued_media_items`, `is_dynamic` recomputed via `has_dynamic_source()`, and the play-action
flag reset. Two cache categories: `CACHE_CATEGORY_PLAYER_QUEUE_STATE` and
`CACHE_CATEGORY_PLAYER_QUEUE_ITEMS`. Writes are debounced and skip volatile elapsed-time fields.
The legacy top-level cache layout is still supported. Replace the round-1 description of
`PlayerQueue.from_dict()` plus a `from_cache()` mashumaro hook.

## Per-queue configuration

New section: crossfade, overlay (#4674), volume normalization, and smart shuffle are queue-scoped
with global defaults (#4373, #4537). Cross-link `02-configuration.md` (Phase 3) and the in-tree
README's configuration section instead of restating every key.

## `10-streaming-pipeline.md` boundary patch

Small and targeted; the rest of that file is Phase 8.

- Both `/single/` and `/flow/` validate against `PlayerQueueData.session_id` via
  `mass.player_queues.queue_data()`. The doc's claim that flow mode does **not** enforce a session
  is wrong.
- `_prepare_next_audio_buffer()` → `player_queues.prepare_next_audio_buffer()` in
  `stream_feeder.py`, called from `streams/audio.py` roughly 60s before track end.
- `flow_mode_stream_log` lives on `PlayerQueueData` and is manipulated from `streams/audio.py`.
- Worth adding: the `track_loaded_in_buffer` → `_preload_next_item` chain.

## Verification

- `rg "PlayerQueueData|ManagedPool|_enter_dynamic_mode|_fill_dynamic_tracks|_fill_autoplay_tracks|SmartShuffle|prepare_next_audio_buffer|has_dynamic_source"`.
- Confirm removals: `rg "_fill_radio_tracks|radio_mode_base_tracks|RADIO_TRACK_MAX_DURATION_SECS|items_last_updated"`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): player queues package, dynamic playlists, autoplay and smart shuffle

Phase 7 of the upstream/dev refresh.
```

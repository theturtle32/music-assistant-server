---
name: arch_docs_v2_phase12_plugin_system
overview: "Phase 12. Rewrite the core of 11-plugin-system.md: PR #3938 deleted PluginSource and replaced it with first-class MediaType.AUDIO_SOURCE MediaItems, moving control to on_source_control/on_volume_change hooks, ownership to queue-scoped selection lifecycle hooks, and playback to the normal queue and stream paths. Also correct every receiver-plugin section, especially Spotify Connect."
todos:
  - id: preflight
    content: "Pre-flight: verify the PluginProvider surface, AudioSource flow, and each receiver plugin against the working tree"
    status: completed
  - id: core_model
    content: "11-plugin-system.md: replace the PluginSource section with the AudioSource MediaItem model"
    status: completed
  - id: base_class
    content: "11-plugin-system.md: rewrite the PluginProvider base class surface and feature matrix"
    status: completed
  - id: integration
    content: "11-plugin-system.md: rewrite registration, source resolution, active source detection, and the sequence diagram"
    status: completed
  - id: ownership
    content: "11-plugin-system.md: replace in_use_by semantics with queue-scoped selection lifecycle and stream_session_id guards"
    status: completed
  - id: delivery
    content: "11-plugin-system.md: fix audio delivery (stream types, queue-item URLs, WAV passthrough, silence keepalive)"
    status: completed
  - id: taxonomy
    content: "11-plugin-system.md: rebuild the plugin taxonomy table from the actual manifests"
    status: completed
  - id: receivers
    content: "11-plugin-system.md: rewrite Spotify Connect and correct AirPlay Receiver, VBAN, and Yandex Ynison"
    status: completed
  - id: bridges
    content: "11-plugin-system.md: update the bridge and feature plugin sections (Party shared playback, Yandex Smart Home, Plex Connect); fix misclassifications"
    status: completed
  - id: keyfiles
    content: "11-plugin-system.md: refresh Key Files and remove obsolete symbols"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 12 — Plugin system: the AudioSource rewrite

File: `docs/architecture/11-plugin-system.md`. The single most invalidated doc in the tree — roughly
60% of it describes an abstraction that no longer exists.

Phase 13 adds the new plugin ecosystem sections and the AI doc. Keep this phase focused on the core
model and the receivers the doc already covers.

## The core change: #3938

**`PluginSource` is gone.** Receiver plugins expose **`AudioSource` MediaItems**
(`MediaType.AUDIO_SOURCE`, defined in `music_assistant_models`) via
`PluginProvider.get_audio_sources()`. Playback is the standard queue flow:
`player_queues.play_media(uri)` → queue item → the streams controller serves
`/single/{session}/{queue}/{item}/{player}.wav`, with WAV passthrough preferred for PCM sources.

| Old (documented) | Current |
| --- | --- |
| `get_source() → PluginSource` | `get_audio_sources() → list[AudioSource]` |
| Callback fields on `PluginSource` (`on_play`, `on_pause`, `on_next`, `on_previous`, `on_seek`, `on_volume`, `on_select`) | `on_source_control(source_id, SourceControl, value=None)` for PLAY/PAUSE/NEXT/PREVIOUS/SEEK; `on_volume_change(source_id, volume)` |
| Ownership via `in_use_by` | `on_source_selected(source_id, player_id, queue_id, stream_session_id)` / `on_source_unselected(...)` |
| `get_audio_stream(player_id)` | `get_stream_details(source_id, queue_id)` + `get_audio_stream(streamdetails, seek_position=0)` |
| Metadata on `PluginSource.metadata` | `StreamDetails.stream_metadata` via `mass.streams.update_stream_metadata(...)` |
| `get_tts_message`, `ai_query` | **unchanged** — still optional hooks gated by `ProviderFeature.TTS` / `AI_QUERY` |

`AudioSource` fields to document: `exclusive`, `can_initiate`, `allow_external_trigger`, and the
capability flags. Note the terminology change: the doc's `passive = False` is now
`can_initiate` / `allow_external_trigger`.

New in #3811 / #3978: `PluginProvider` also implements music features — `browse`, `search`,
`get_similar_tracks`, `get_recommendations`, `get_recommendation_items`, `get_playlist`,
`get_playlist_tracks`. The feature matrix should cover `AUDIO_SOURCE`, `BROWSE`, `SEARCH`,
`RECOMMENDATIONS`, and `SIMILAR_TRACKS`, not just the four documented methods.

## Integration flow (rewrite)

Several claims are now actively wrong:

- **`Player.__final_source_list` no longer appends plugin sources.** It only ensures the MA Queue
  entry exists. Audio sources are discovered through **music browse** (the root browse tree
  surfaces `ProviderFeature.AUDIO_SOURCE` providers as "Live Inputs") and played with `play_media`.
  Cross-link Phase 10.
- **`__final_active_source` no longer checks plugin sources or `in_use_by`.** It resolves group /
  sync parent, protocol parent, `__active_mass_source`, or the player-reported source. AudioSource
  activity is queue-based.
- **`get_plugin_sources()` / `get_plugin_source()` are removed.** Active source detection is
  `_get_active_audio_source(player)` in `controllers/players/controller.py`, which inspects whether
  the player's active queue item is an `AudioSource`.
- **Legacy compatibility:** `select_source(plugin_instance_id)` is translated into `play_media`, but
  only for single-source plugins. Document it as a compatibility shim.
- Rewrite the sequence diagram: `play_media(AudioSource URI)` → queue item → the streams HTTP GET
  fires `on_source_selected` → `get_stream_details` → stream; commands route via
  `_get_active_audio_source` → `on_source_control` / `on_volume_change`.
- `PluginSource.metadata.elapsed_time` driving player progress becomes
  `StreamDetails.stream_metadata.elapsed_time` on the active queue item, updated via
  `mass.streams.update_stream_metadata()` and read from `current_item.streamdetails`. Round 1 added
  the `elapsed_time` note — update the mechanism, keep the insight.

## Ownership

Replace the `in_use_by` section. Ownership is **queue-scoped**: providers keep an internal
`_in_use_by_queue`, claimed in `on_source_selected` and released in `on_source_unselected`, with
`stream_session_id` acting as a stale-release guard. Volume goes to the direct queue owner once via
`on_volume_change(source_id, volume)` — cross-link Phase 5, which fixes the volume doc.

## Audio delivery

- **Spotify Connect no longer uses `StreamType.NAMED_PIPE`** — it is `StreamType.CUSTOM` reading
  go-librespot stdout. AirPlay Receiver still uses `NAMED_PIPE`; AriaCast and VBAN remain `CUSTOM`.
- The `/pluginsource/{source_id}/{player_id}.{fmt}` URL on port 8097 no longer exists; delivery is
  through standard queue-item stream URLs, with `resolve_stream_url` forcing WAV for `AUDIO_SOURCE`.
  Cross-link Phase 8.
- Add the silence contract: `CUSTOM` streams get server-side silence keepalive, while `NAMED_PIPE`
  producers must keep writing silence themselves.

## Taxonomy

Rebuild from the manifests — `rg -l '"type": "plugin"' music_assistant/providers/*/manifest.json` —
rather than trusting the audit snapshot. As of the audit there were 21 production plugins, and the
doc's three-category table needs roughly six or seven categories: receiver, scrobbler, external
control bridge, HA bridge (+ AI/TTS backend), guest/social, library/discovery, and diagnostics.

Two misclassifications to avoid: **`teddycloud`** is a music provider and **`msx_bridge`** is a
player provider — neither belongs in the plugin taxonomy. **`plex_connect`** is a bridge, not a
receiver (it declares no `AUDIO_SOURCE`).

## Receiver plugins

- **Spotify Connect — near-total rewrite.** It now uses **go-librespot** with an HTTP + WebSocket
  API (`GoLibrespotClient`), `StreamType.CUSTOM` from stdout, and **no** Spotify music provider or
  Web API dependency. `can_play_pause` / `can_seek` / `can_next_previous` are static `True` rather
  than dynamic. Volume scale is `VOLUME_STEPS=100`, not 0–65535. External sessions trigger a
  debounced `player_queues.play_media(uri)` instead of `select_source()`. Metadata flows through
  `update_stream_metadata`. Anti-ping-pong uses `_last_volume_sent` plus
  `INITIAL_VOLUME_GRACE_S=3`.

  This is directly relevant to the fork's volume-echo work — note the upstream mechanism accurately
  rather than describing the fork's approach. `providers/spotify_connect/ARCHITECTURE.md` is the
  in-tree reference; link to it (Phase 1 may have refreshed it).
- **AirPlay Receiver:** volume is applied via `_handle_volume_change` → `cmd_volume_set`, not an
  `on_volume` callback; metadata is pushed via `update_stream_metadata`; `on_source_control` is a
  no-op; the source is `can_initiate=False`, so MA-initiated playback requires starting from the
  Live Inputs browse entry.
- **VBAN Receiver:** `can_initiate=True`; discovered through browse, not the player source list.
- **Yandex Music Connect (Ynison):** uses `on_source_control` and a multi-track `CUSTOM`
  `get_audio_stream`. **`on_volume_change` is not implemented** — there is no volume sync, which
  contradicts the round-1 text. Manifest stage is now `stable`. Still depends on the `yandex_music`
  provider for track URLs.

## Bridges and feature plugins

- **Party** now uses `SharedPlaybackSession` (`helpers/shared_playback.py`) with `VENUE` (real
  player) and `REMOTE` (Sendspin virtual player) modes, plus `party/listen_in`,
  `party/stop_listen_in`, and `party/can_listen_in`. The queue behavior described is still broadly
  right. Phase 13 documents shared playback in depth; here just correct the Party section and
  cross-link.
- **Yandex Smart Home:** still accurate, but `auto_skill.py` was deleted and the auto-create logic
  moved to `_smarthome_auto_create.py` (smart-home URL derivation only; the Alice skill branch is
  gone).
- **Snapcast** is a player provider, not a plugin, but it does consume `MediaType.AUDIO_SOURCE`
  queue items with queue-scoped stream naming. Mention it as a consumer and cross-link Phase 8
  rather than adding it to the taxonomy.
- **Dashie Kiosk** was deleted (#4192) and was a player provider — if it appears anywhere, remove it.

## Key files

Add `helpers/shared_playback.py`, `controllers/music/controller.py` (AudioSource browse/resolve),
`controllers/streams/controller.py` (lifecycle hooks), and `controllers/player_queues/`. Remove
`PluginSource`, `get_plugin_sources`, and `_handle_select_plugin_source`.

## Verification

- `rg "PluginSource|get_plugin_sources|in_use_by|_handle_select_plugin_source"` in
  `music_assistant/` — should return nothing meaningful. If it does, the model is not as clean as
  described and the doc must say so.
- `rg "get_audio_sources|on_source_control|on_source_selected|on_volume_change|SourceControl"`.
- Sweep the whole docs tree for leftover `PluginSource` references, not just this file.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): rewrite plugin system for first-class AudioSource media items

Phase 12 of the upstream/dev refresh.
```

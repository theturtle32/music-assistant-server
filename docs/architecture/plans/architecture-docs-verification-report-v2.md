# Architecture Documentation Verification Report (v2)

This report details the findings of a precise, code-driven verification pass across the 16 newly generated architecture documents in `docs/architecture/`. This second version of the report relies on exact file paths and line-number-backed analysis of the `music_assistant` Python codebase, filtering out previous false positives and focusing strictly on verified inaccuracies, gaps, and missing cross-domain context.

The findings are grouped by the architectural domains they cover, with specific, actionable recommendations for revising the markdown files.

---

## 1. Core Architecture & Lifecycle
**Target Docs:** `00-overview.md`, `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`

### 1.1 Overview & Event System Nuances
- **Startup Diagram (`00-overview.md`):** The diagram implies `DiscoveryController` is "running" immediately after config initialization. In reality, it is only instantiated at that step; its actual `setup()` runs much later.
- **`SYNC_TASKS_UPDATED` (`01-event-system.md`):** The event table lists `SYNC_TASKS_UPDATED`. This event type does not exist in the codebase and is never signaled. It should be removed.
- **WebSocket Filtering (`01-event-system.md`):** The doc implies a blanket `player_filter` on events. In reality, `websocket_client._subscribe_to_events` only applies the `player_filter` to a specific subset of player/queue events, and it actively rewrites the `TASKS_UPDATED` payload to `list_tasks_for_user`.
- **`@api_command` and `alias` (`01-event-system.md`):** The docs correctly note `alias` on the handler, but it's worth clarifying that the `@api_command` decorator itself does not accept an `alias` parameter. Aliases are only set via dynamic `register_api_command` calls.

### 1.2 Configuration (`02-configuration.md`)
- **Missing DB Table:** The list of library database tables is missing `genre_media_item_exclusion` (defined in `constants.py`).
- **Provider vs. Core Reload Logic:** The doc conflates how providers and core controllers handle config updates. `CoreController.update_config` checks `requires_reload` on the config entries. However, `Provider.update_config` reloads on *any* config change (except log level) and does not consult `requires_reload`.

### 1.3 Provider Lifecycle (`15-provider-lifecycle.md`)
- **`Provider` Base API:** The class diagram lists `+setup()` as an instance method on the `Provider` class. The base class actually exposes `handle_async_init()`, `loaded_in_mass()`, etc. `setup()` is a module-level function returned by `load_provider_module`, not an instance method.
- **Load Concurrency:** The doc should clarify that `loaded_in_mass()` and `run_provider_discovery()` are scheduled as background tasks during `_load_provider`, rather than being awaited in strict sequence before the provider is marked available.
- **Dependent Unloads:** After a successful `load_provider`, the server actively unloads any loaded-but-unavailable providers whose manifest `depends_on` matches the domain that just loaded. This recovery mechanism is undocumented.

---

## 2. Players, Grouping & Volume
**Target Docs:** `03-player-model.md`, `04-player-controller.md`, `05-protocol-linking.md`, `06-grouping.md`, `07-volume.md`

### 2.1 Player Model & Controller (`03-player-model.md`, `04-player-controller.md`)
- **`play()` Feature:** `03-player-model.md` claims `play()` is "*(always available)*". In code, `play()` is abstract and raises `NotImplementedError` if not implemented. It should be documented as "required — must implement".
- **`cmd_play` Routing Table:** `04-player-controller.md` says "If paused with queue -> player_queues.resume". The actual code logic is inverted: if *not* paused and a queue exists, it tries to resume the queue; if paused, it skips queue resume and falls through to `_handle_cmd_play` (native unpause).
- **Plugin `on_stop`:** The command routing diagram in `04-player-controller.md` shows a plugin `on_stop` callback. `PluginSource` has no `on_stop` callback (only `on_pause`, `on_play`, etc.).
- **Queue Resolution (`get_active_queue`):** A major cross-cutting gap. None of the docs explain how the system finds the right queue for a grouped or protocol player. `get_active_queue` follows a strict 4-step resolution chain: sync leader -> active GROUP -> active_source/player_id -> protocol parent.

### 2.2 Grouping (`06-grouping.md`)
- **UGP Dynamic `can_group_with`:** The doc says it returns "all non-UGP provider instances". This behavior (returning all provider `instance_id`s) only applies to dynamic groups, whereas static groups return their static member list.

### 2.3 Volume Mechanics (`07-volume.md`)
- **Sync Leader Routing:** `cmd_group_volume` redirects volume commands from sync followers to the sync leader (calling `set_group_volume` on the leader). This redirect is missing from the doc.
- **Group Mute Asymmetry:** Unlike group volume, `cmd_group_volume_mute` does *not* redirect to the sync leader. Calling group mute on a pure sync child does nothing.
- **`group_volume_muted` Mixed State:** The docs imply `group_volume_muted` is False if any member is unmuted. In reality, it returns `None` when the mute state is *mixed* (some muted, some unmuted).

---

## 3. Media Library, Queues & Streaming
**Target Docs:** `08-media-library.md`, `09-player-queues.md`, `10-streaming-pipeline.md`

### 3.1 Media Library (`08-media-library.md`)
- **Global Search Limitation:** `MusicController.search_library` does not populate `MediaType.GENRE`. Global searches will not return library genres through this path, even though a genre controller exists.
- **URI Parsing:** The table labels `https://open.*` as Spotify-only. `parse_uri` treats any `https://open.` URL as shareable, explicitly supporting Qobuz alongside Spotify.

### 3.2 Player Queues (`09-player-queues.md`)
- **`play_index` Retry Logic:** When `play_index` fails and advances to the next track, it uses `allow_repeat=False`. This error recovery behavior means repeat-all will not wrap around if it is skipping failed items.
- **Flow Stream Completion:** After a flow stream finishes, `queue_buffer_completed` can resume playback after idle if new items appeared. This recovery path is undocumented.
- **Resume Position:** `play_index` sets `seek_position` from `resume_position_ms` for podcast episodes and audiobooks.

### 3.3 Streaming Pipeline (`10-streaming-pipeline.md`)
- **Auth & `get_stream_details`:** The doc incorrectly calls `provider_filter` an optional per-player filter. It actually uses the *playback user's* `provider_filter`, evaluated in a two-phase loop (preferred providers first, then all others).
- **Normalization Modes:** The table is missing `FALLBACK_FIXED_GAIN`, which is used when no loudness measurement is available.
- **DSP vs Grouping:** `get_player_filter_params` uses `is_grouping_preventing_dsp` to disable DSP entirely in unsupported group setups. This cross-domain interaction is missing.
- **Flow Throttling:** Flow streams use `-readrate` and `-readrate_initial_burst 6` for Chromecast-style clients.

---

## 4. Plugins, API & Infrastructure
**Target Docs:** `11-plugin-system.md`, `12-webserver-api.md`, `13-discovery.md`, `14-metadata.md`

### 4.1 Plugin System (`11-plugin-system.md`)
- **Select-Source Order:** The doc shows `on_select()` being called before `in_use_by` is set. The code actually sets `in_use_by = player_id` *first*, and then calls `on_select()`.
- **`__final_source_list`:** The doc says it appends "all non-passive plugin sources". The code actually appends *every* plugin source without a passive filter.
- **Plugin Stream URL:** The URL includes a format suffix (e.g., `.wav`), making the true format `/pluginsource/{source_id}/{player_id}.{fmt}`.
- **Callback Signatures:** The table uses `() -> None`, but implementations are `async def` (`Awaitable[None]`).

### 4.2 Webserver & API (`12-webserver-api.md`)
- **HTTP JSON-RPC Response:** The doc says the HTTP JSON-RPC flow ends with a `SuccessResultMessage`. In reality, the HTTP handler returns a raw JSON body (`web.json_response(result)`). The `SuccessResultMessage` envelope is only used for WebSockets.
- **Dynamic API Registration:** Party mode and genre APIs use `mass.register_api_command` dynamically at runtime. The doc implies `MusicAssistant` scans "all controllers" for `@api_command` decorators, but it actually scans a fixed list of core controllers.

### 4.3 Discovery & Metadata (`13-discovery.md`, `14-metadata.md`)
- **Image Proxy Dual Mount:** `14-metadata.md` says `/imageproxy` is on the streams server (8097). It is actually mounted on *both* the webserver (8095) and the streams server.
- **MetadataProvider Default:** If a feature is declared but not overridden, it raises `NotImplementedError`; it does not return `None` silently.

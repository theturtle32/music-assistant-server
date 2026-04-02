# Architecture Documentation Verification Report

This report details the findings of a comprehensive, code-driven verification pass across the 16 newly generated architecture documents in `docs/architecture/`. The goal of this verification was to cross-reference the documentation against the actual Music Assistant Python codebase to identify gaps, inaccuracies, stale references, and missing cross-domain context.

The findings are grouped by the architectural domains they cover, with specific, actionable recommendations for revising the markdown files.

---

## 1. Core Architecture & Lifecycle
**Target Docs:** `00-overview.md`, `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`

### 1.1 Inaccurate File References
- **Issue:** The documentation frequently references `music_assistant/server.py` and `music_assistant/controllers/events.py`. Neither of these files exist in the current codebase layout.
- **Code Reality:** The core process hub, event bus (`signal_event`, `subscribe`), and provider registry all live in **`music_assistant/mass.py`** (`MusicAssistant` class).
- **Recommendation:** Update `00-overview.md` and `01-event-system.md` to point to `mass.py` and explicitly state that there is no standalone `EventsController`.

### 1.2 Event System Nuances (`01-event-system.md`)
- **`@api_command` and `alias`:** The doc claims the `@api_command` decorator sets an `alias` attribute. In reality, the decorator (`helpers/api.py`) only sets `api_cmd`, `api_authenticated`, and `api_required_role`. The `alias=True` parameter is only used with dynamic registration via `MusicAssistant.register_api_command()`.
- **Queue Subscriptions:** The sequence diagram shows `PlayerQueuesController` subscribing to the event bus. In code, queue updates are driven from queue/player code paths that call `signal_event` directly; the controller itself does not call `mass.subscribe`.
- **WebSocket Filtering:** The doc implies a blanket `player_filter` on events. In reality, `websocket_client._subscribe_to_events` only applies the `player_filter` to a specific subset of player/queue events, and it actively rewrites the `TASKS_UPDATED` payload to `list_tasks_for_user`.
- **Stale Events:** The doc lists `SYNC_TASKS_UPDATED`, which is defined in the models package but never actually signaled by the server codebase. Additionally, `EventType.SHUTDOWN` is marked as deprecated in favor of `CORE_STATE_UPDATED`, but `aiohttp_client.py` still subscribes to `SHUTDOWN`.

### 1.3 Configuration (`02-configuration.md`)
- **Missing DB Table:** The list of library database tables is missing `genre_media_item_exclusion` (defined in `constants.py`).
- **Provider Logger Updates:** The doc notes that log level changes apply immediately. The code also treats provider `name` changes as triggering an immediate logger update (`_set_log_level_from_config`), as the child logger name must switch.

### 1.4 Provider Lifecycle (`15-provider-lifecycle.md`)
- **`Provider` Base API:** The class diagram lists `setup()` on the `Provider` instance. The base class actually exposes `handle_async_init()`, `loaded_in_mass()`, `unload()`, and `update_config()`. The `setup()` function is a module-level entrypoint, not an instance method.
- **Load Concurrency (Critical):** The flowchart suggests a strict finish-before-next-step pipeline. In `mass.py`, `_load_provider` schedules `loaded_in_mass()` and `run_provider_discovery()` as background tasks without awaiting them, then immediately signals `PROVIDERS_UPDATED` and calls controller hooks. This means discovery and `loaded_in_mass` may still be in flight when the system announces the provider is loaded.
- **Dependent Unloads:** After a successful `load_provider`, the server actively unloads any loaded-but-unavailable providers whose manifest `depends_on` matches the domain that just loaded. This recovery mechanism is undocumented.
- **`on_provider_loaded` Scoping:** The doc implies all controllers get an `on_provider_loaded` hook. Only `MusicController` and `PlayerController` are invoked from `mass._load_provider`. Metadata and streams integrate via `loaded_in_mass()` and discovery.

---

## 2. Players, Grouping & Volume
**Target Docs:** `03-player-model.md`, `04-player-controller.md`, `05-protocol-linking.md`, `06-grouping.md`, `07-volume.md`

### 2.1 Player Model & Controller (`03-player-model.md`, `04-player-controller.md`)
- **`play()` Feature:** The doc claims `play()` is "(always available)". In code, `play()` is abstract and raises `NotImplementedError` if not implemented. It is required for providers that receive play/unpause on the device path, but it is not a feature-less universal command.
- **Universal Player Typing:** The docs (`03` and `05`) state that `UniversalPlayer` uses `PlayerType.GROUP` in config for the UI, but `PLAYER` on the class. In reality, `ConfigController.create_default_player_config` reconciles the stored config to match the class type (`PLAYER`) when the instance is created.
- **`cmd_play` Routing Table:** The doc says "If paused with queue -> `player_queues.resume`". The code actually does the opposite: if *not* paused, it tries to resume the queue; if paused, it skips queue resume and goes directly to `_handle_cmd_play` (unpause, plugin `on_play`, etc.).
- **Plugin `on_stop`:** The command routing diagram shows a plugin `on_stop` callback. `PluginSource` only has `on_pause`, `on_play`, `on_next`, `on_previous`, `on_seek`, and `on_volume`. Stop paths do not invoke a plugin stop callback.
- **Queue Resolution (`get_active_queue`):** A major cross-cutting gap. None of the docs explain how the system finds the right queue for a grouped or protocol player. `get_active_queue` follows the sync leader, then active GROUP player, then `active_source`/player ID, then PROTOCOL parent's queue.

### 2.2 Grouping (`06-grouping.md`)
- **`active_only` Semantics:** The doc says `iter_group_members(..., active_only=True)` checks if `active_group` matches. Specifically, it requires `child_player.state.active_group == group_player.player_id`.
- **UGP Dynamic `can_group_with`:** The doc says it returns "all non-UGP provider instances". The code returns the `instance_id` of every `PlayerProvider` except the UGP provider itself.

### 2.3 Volume Mechanics (`07-volume.md`)
- **Volume Normalization (Major Gap):** `07-volume.md` completely misses loudness normalization. It must explain that UI volume (device level) is separate from loudness normalization (DSP/FFmpeg level pipeline), bridging the gap to `10-streaming-pipeline.md`.
- **Sync Leader Routing:** `cmd_group_volume` redirects volume commands from sync followers to the sync leader (calling `set_group_volume` on the leader). This is missing from the doc.
- **Group Mute Asymmetry:** Unlike group volume, `cmd_group_volume_mute` does *not* redirect to the sync leader. Calling group mute on a pure sync child does nothing.
- **`set_group_volume` No-op:** If `group_player.state.group_volume` is `None` (no supported volumes on members), `set_group_volume` returns immediately without making changes.

---

## 3. Media Library, Queues & Streaming
**Target Docs:** `08-media-library.md`, `09-player-queues.md`, `10-streaming-pipeline.md`

### 3.1 Media Library (`08-media-library.md`)
- **User Provider Filter:** The snippet for `get_unique_providers()` omits that it applies the *current user's* `provider_filter` (for non-admin users).
- **Global Search Limitation:** `MusicController.search_library` does not populate `MediaType.GENRE`. Global searches will not return library genres through this path, even though a genre controller exists.
- **URI Parsing:** The table labels `https://open.*` as Spotify-only. `parse_uri` treats any `https://open.` URL as shareable, explicitly supporting Qobuz as well.

### 3.2 Player Queues (`09-player-queues.md`)
- **`play_index` Retry Logic:** When `play_index` fails and advances to the next track, it uses `allow_repeat=False`. This means repeat-all will not wrap around if it is skipping failed items.
- **Pre-warm and `get_active_queue`:** In `StreamsAudio`, `_prepare_next_audio_buffer` relies on `get_active_queue()`. This means grouped players pre-warm based on the group's queue, not their individual naive `player_id` queue.
- **Flow Stream Completion:** After a flow stream finishes, `StreamsAudio` calls `player_queues.queue_buffer_completed`, which can resume playback after idle if new items appeared. This recovery path is undocumented.
- **Resume Position:** `play_index` sets `seek_position` from `resume_position_ms` for podcast episodes and audiobooks.

### 3.3 Streaming Pipeline (`10-streaming-pipeline.md`)
- **Auth & `get_stream_details`:** The doc incorrectly calls `provider_filter` an optional per-player filter. It is actually the *playback user's* `provider_filter`, evaluated in a two-phase loop (preferred providers first, then all others).
- **Stream Details Reuse:** Stream details are reused not just if the buffer is valid, but also if `created_at + expiration` is still in the future.
- **Normalization Modes:** The table is missing `FALLBACK_FIXED_GAIN`, which is used when there is no loudness measurement.
- **DSP vs Grouping:** `get_player_filter_params` uses `is_grouping_preventing_dsp` to disable DSP entirely in unsupported group setups. This cross-domain interaction is missing.
- **Crossfade Constraints:** Crossfade can be skipped when current/next sample rates differ, unless `CONF_ENTRY_CROSSFADE_DIFFERENT_SAMPLE_RATES` allows it.
- **Flow Throttling:** Flow streams use `-readrate` and `-readrate_initial_burst 6` for Chromecast-style clients.

---

## 4. Plugins, API & Infrastructure
**Target Docs:** `11-plugin-system.md`, `12-webserver-api.md`, `13-discovery.md`, `14-metadata.md`

### 4.1 Plugin System (`11-plugin-system.md`)
- **Select-Source Order:** The doc shows `on_select()` being called before `in_use_by` is set. The code actually sets `in_use_by = player_id` *first*, and then calls `on_select()`.
- **`__final_source_list`:** The doc says it appends "all non-passive plugin sources". The code actually appends *every* plugin source without a passive filter.
- **Active Source Resolution:** The doc claims `__final_active_source` checks `in_use_by` OR `active_source == plugin_id`. The serialized state only uses `in_use_by` for plugin takeover. Command routing (`_get_active_plugin_source`) checks both.
- **Plugin Stream URL:** The URL includes a format suffix (e.g., `.wav`), making the true format `/pluginsource/{source_id}/{player_id}.{fmt}`.
- **Callback Signatures:** The table uses `() -> None`, but implementations are `async def` (`Awaitable[None]`).
- **Volume Anti-Ping-Pong:** There are two mechanisms: `_on_volume` skips sending to Spotify if the volume matches what was just sent, AND inbound `volume_changed` ignores the first 3 seconds after `session_connected`.

### 4.2 Webserver & API (`12-webserver-api.md`)
- **Missing Routes:** The route table is missing `HEAD /`, `GET /logo.png`, `GET /resources/common.css`, `POST /auth/logout`, `PATCH /auth/me`, and `OPTIONS /auth/login`.
- **Dynamic API Registration:** Party mode and others use `mass.register_api_command` dynamically, which should be distinguished from the static `@api_command` decorator. Aliases are omitted from generated docs.
- **WebSocket Setup:** WS connections send `server_info` first, then may return `503 Setup required` if no users exist and it's not an ingress connection (symmetric with HTTP `/api`).
- **`provider_filter`:** This filter is used for API/data paths, but is *not* used in `websocket_client` for event fan-out (only `player_filter` is).

### 4.3 Discovery & Metadata (`13-discovery.md`, `14-metadata.md`)
- **Bluesound mDNS:** The doc lacks concrete types. The manifest uses `_musc._tcp.local.` and `_musp._tcp.local.`.
- **Image Proxy Dual Mount:** The doc says `/imageproxy` is on the streams server (8097). It is actually mounted on *both* the webserver (8095) and the streams server.
- **ProviderFeature Names:** The table uses shorthand (`ARTIST`, `ALBUM`). It should use the actual enum names (`ProviderFeature.ARTIST_METADATA`, etc.).
- **MetadataProvider Default:** If a feature is declared but not overridden, it raises `NotImplementedError`; it does not return `None` silently.
- **Phase 2 vs Lyrics:** Phase 2 enrichment loops over providers with `TRACK_METADATA`. `LYRICS` is an extra capability; on-demand lyrics use `metadata/get_track_lyrics`.

---

## Next Steps
To finalize the documentation, a maintainer or agent should iterate through the 16 markdown files in `docs/architecture/` and apply the corrections outlined in this report. Once applied, the documentation will accurately reflect the current state of the `music_assistant` codebase.

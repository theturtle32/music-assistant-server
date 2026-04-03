# Independent Architecture Verification Report (Gemini 3.1 Pro) v3

This report details the findings of a rigorous, code-driven verification of the Music Assistant architectural documentation against the actual Python implementation in the `music_assistant/` directory.

---

## 1. Core, Events, Config, & Provider Lifecycle
**Scope:** `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`

### Verified Accuracies
*   **Event Pub/Sub Backbone:** `signal_event` correctly implements the early return on closing, thread checks, and async/sync dispatch as documented (`music_assistant/mass.py` lines 419-448). `subscribe` normalizes inputs and returns an unsubscribe closure (`mass.py` lines 450-473).
*   **API Command Registration:** `_register_api_commands` dynamically scans core controllers, skipping dunder names and properties (`mass.py` lines 767-796). `APICommandHandler` dataclass matches the documented shape (`helpers/api.py` lines 270-280).
*   **Config Initialization:** `ConfigController` is set up first in `start()` before manifests/controllers (`mass.py` lines 144-149). It uses a debounced save mechanism with `DEFAULT_SAVE_DELAY = 5` (`controllers/config.py` lines 1289-1301).
*   **Database & Cache:** SQLite PRAGMAs (e.g., `journal_mode=WAL`, `synchronous=normal`) match the docs (`helpers/database.py` lines 109-117). Memory cache size is 500, and items with TTL < 1800s skip DB writes (`controllers/cache.py` lines 57, 188-192).
*   **Provider Startup Order:** Built-in providers are loaded first, followed by regular providers via `TaskManager` if not in safe mode (`mass.py` lines 203-209).
*   **Provider Dependency Reloading:** `load_provider_config` correctly reloads dependent providers whose manifest `depends_on` matches the loaded domain (`mass.py` lines 634-655).

### Inaccuracies & Stale Info
*   **Event Logging (`QUEUE_TIME_UPDATED`):** `01-event-system.md` claims `QUEUE_TIME_UPDATED` is not special-cased but a comment says it is. In reality, the code *does* log it at `VERBOSE_LOG_LEVEL` without a guard (`mass.py` lines 431-433). The comment is stale.
*   **API Command Aliases:** The docs claim decorators can set `alias=True`. However, `_register_api_commands` *never* reads an alias flag from decorated methods; it always defaults to `False` unless explicitly registered via `register_api_command` (`mass.py` lines 767-796).
*   **`ConfigController.close()`:** The doc says it "forces any pending save". The code only saves if `_timer_handle` is active; otherwise, it returns early (`controllers/config.py` lines 189-195).
*   **Provider Instance IDs:** The doc says they are "auto-generated `shortuuid`". The code actually uses `{domain}--{shortuuid.random(8)}` (`controllers/config.py` line 1628).
*   **Concurrency Limit:** `15-provider-lifecycle.md` implies unlimited concurrency for regular provider loading, but the code uses a semaphore limit of 2: `TaskManager(self, 2)` (`mass.py` lines 882-887).
*   **`Provider.unload_with_error` Footgun:** The implementation passes the error string as the second positional argument to `unload_provider` (which expects `is_removed: bool`), making it buggy if used (`models/provider.py` lines 163-165). The documented path `unload_provider_with_error` on `MusicAssistant` is correct.

### Missing Cross-Cutting Context
*   **Task Management (`create_task`):** `create_task` is central to events and lifecycle, supporting `eager_start`, task deduplication, and cancellation on `stop()` (`mass.py` lines 475-541). This operational contract is missing from the event docs.
*   **Config Saves vs Cancellation:** `save_core_config` deliberately saves first and catches `asyncio.CancelledError` around `update_config` to tolerate reloads that cancel the current task (`controllers/config.py` lines 1159-1168).
*   **Provider Name Changes:** When a provider's `name` changes, config explicitly signals `PROVIDERS_UPDATED` (`controllers/config.py` lines 1577-1579). This config-driven emission path is missing from the lifecycle docs.
*   **`get_providers()` Auth Context:** Internal `signal_event(..., data=self.get_providers())` uses the API command `get_providers`, which applies user provider filters when `get_current_user()` is set. The relationship between WebSocket/client context and event payloads is undocumented.

---

## 2. Players, Grouping, & Volume
**Scope:** `03-player-model.md`, `04-player-controller.md`, `06-grouping.md`, `07-volume.md`

### Verified Accuracies
*   **Player Registration:** The complex registration pipeline (`_register_lock`, MAC enrichment, throttler setup, config loading) is accurately reflected (`controllers/players/controller.py` lines 1280-1401).
*   **`Player.update_state()` Pipeline:** Includes event-loop check, cache clear, debounced `_on_player_media_updated`, and `signal_player_state_update` (`models/player.py` lines 1196-1225).
*   **Group Volume:** `set_group_volume` correctly averages member volumes, calculates deltas, and uses `asyncio.gather` to apply changes (`controller.py` lines 1739-1758).
*   **Universal Group Stream (UGP):** Routes `/ugp/{player_id}.flac|.mp3|.aac` and uses a queue-based runner with `asyncio.sleep(0.25)` and `-readrate 1.1` (`providers/universal_group/ugp_stream.py` lines 74-123).

### Inaccuracies & Stale Info
*   **Mixed Mute State:** `03-player-model.md` says `group_volume_muted` is `None` if no members support mute. `07-volume.md` says it's `None` if mixed *or* unsupported. The code (`player.py` lines 874-908) returns `None` for both mixed states and unsupported states. `07` is correct; `03` is incomplete.
*   **`PLAYER_UPDATED` on Temporary Unregister:** `04-player-controller.md` implies a standard payload. The code emits `data=player.state` (frozen snapshot), not `data=player` (`controller.py` lines 1462-1468).
*   **Group `set_members` Delegation:** `06-grouping.md` claims `PlayerType.GROUP` always delegates to `player.set_members()`. The code only delegates if `PlayerFeature.SET_MEMBERS` is in `supported_features` (`controller.py` lines 2607-2621). Static groups often drop this feature.
*   **`cmd_group_many` Decorator:** `06-grouping.md` lists `cmd_group_many` like other commands. In code, it has `@api_command` only—no `@handle_player_command` (no automatic protocol-parent rewrite, throttling, or permission check) (`controller.py` lines 1114-1122).
*   **Announcement Volume Math:** `07-volume.md` gives an example of "current × 1.5". The code uses `volume_level = int(volume + (volume/100) * strategy_volume)` (`controller.py` lines 1783-1788). A factor of 1.5 requires `strategy_value = 50`, not "1.5".

### Missing Cross-Cutting Context
*   **`cmd_set_members` Gate:** Any target must advertise `SET_MEMBERS` in `state.supported_features` (`controller.py` lines 1078-1080). Static group players often do not, shaping what the API can do vs internal `_handle_set_members`.
*   **`signal_player_state_update` Side Effects:** Includes debounced queue updates, DSP reload on `group_members` changes, external-source takeover timer (5s), and elapsed-only short circuits (`controller.py` lines 1541-1619).
*   **Volume UX for Sync Leaders:** `cmd_volume_up`/`down` only redirect to group volume when `type == GROUP`. A standard `PLAYER` acting as a sync leader steps its *own* volume, not the group volume (`controller.py` lines 636-659).
*   **Plugin Volume Hooks:** Plugin `on_volume` runs *in addition* to hardware routing, not as a replacement (`controller.py` lines 2915-2923).

---

## 3. Media Library, Queues, & Streaming Pipeline
**Scope:** `08-media-library.md`, `09-player-queues.md`, `10-streaming-pipeline.md`

### Verified Accuracies
*   **Library Search:** The search flow correctly uses `asyncio.gather` over unique providers, interleaves results with `zip_longest`, and caches for 600s (`controllers/music.py` lines 308-451).
*   **Queue Play Actions:** The `@handle_play_action` decorator correctly enforces a per-queue lock and sets `ATTR_PLAY_ACTION_IN_PROGRESS` (`controllers/player_queues.py` lines 125-179).
*   **Pre-warm Path:** `get_queue_item_stream` triggers at `duration - 60` (via consumed position) and calls `_prepare_next_audio_buffer` (`controllers/streams/audio.py` lines 1337-1348).
*   **Flow Mode:** Uses `queue.flow_mode = True`, `load_next_queue_item` loop, and transitions to `STANDARD_CROSSFADE` if smart fading yields minimal buffering (`audio.py` lines 1664-1689).

### Inaccuracies & Stale Info
*   **Sync Interval:** `08-media-library.md` claims the sync interval is configured via `CONF_SYNC_INTERVAL`. This constant is entirely unused in the scheduling path; the code uses per-provider `library_sync_{media_type}s` config (`music.py` lines 2094-2114).
*   **Track Comparison Order:** The doc's ordered list for track comparison is slightly off. The code uses `compare_item_ids`, primary externals (MB recording/track, AcoustID), secondary externals (incl. ISRC with 8s duration), then title/artists/version, then album/disc/track alignment (`helpers/compare.py` lines 139-215).
*   **Loudnorm Parameters:** `10-streaming-pipeline.md` lists `TP=-1:LRA=14`. The code actually uses `TP=-2.0:LRA=10.0` (`audio.py` lines 1249-1253).
*   **Play Action Lock Timeout:** `09-player-queues.md` fails to mention the critical 60-second lock acquisition timeout and forced lock replacement (`player_queues.py` lines 156-167).
*   **Inactive Queue State:** The doc states an inactive queue is forced to IDLE. The code sets IDLE only when inactive *and* `queue_id not in _prev_states` (`player_queues.py` lines 1364-1374).

### Missing Cross-Cutting Context
*   **Auth, Users, and Throttling:** `get_stream_details` and `_load_item` set `BYPASS_THROTTLER` for playback priority (`audio.py` lines 222-232). The user `provider_filter` affects stream provider resolution (`audio.py` lines 188-197).
*   **Pre-warm Queue Resolution:** The pre-warm gate uses `get_active_queue(queue_item.queue_id)` before warming the next buffer (`audio.py` lines 1339-1348). Active-queue resolution (sync leaders vs children) applies *before* streaming pipeline decisions.
*   **Playback Progress to Telemetry:** `_handle_playback_progress_report` explicitly calls `mass.music.mark_item_played` and emits `MEDIA_ITEM_PLAYED` (`player_queues.py` lines 3048-3067), tying queues directly to the library playlog.

---

## 4. Plugins, Webserver API, Discovery, & Metadata
**Scope:** `11-plugin-system.md`, `12-webserver-api.md`, `13-discovery.md`, `14-metadata.md`

### Verified Accuracies
*   **Plugin Sources:** `get_plugin_sources` correctly filters for `ProviderType.PLUGIN` with `ProviderFeature.AUDIO_SOURCE` (`controllers/players/controller.py` lines 406-433).
*   **Webserver Core Routes:** Routes like `/`, `/ws`, `POST /api`, `/imageproxy`, `/login`, and `/sendspin` are correctly implemented (`controllers/webserver/controller.py` lines 259-308).
*   **mDNS Browser:** The discovery controller aggregates mDNS types over the union of `mdns_discovery` lists from all manifests (`controllers/discovery/controller.py` lines 165-181).
*   **Metadata Throttling:** Uses `Throttler(1, 30)` and a `REFRESH_INTERVAL` of 90 days (`controllers/metadata.py` lines 134, 161).

### Inaccuracies & Stale Info
*   **`__final_active_source` Ordering:** `11-plugin-system.md` implies plugin override happens immediately. The code applies it *only after* group/sync and protocol-parent logic (`models/player.py` lines 1929-1985).
*   **Webserver Routes:** `12-webserver-api.md` misses several core routes, including `HEAD /`, `/preview`, `/info`, `/setup`, and the HTML API doc routes (`/api-docs/commands`, etc.) (`webserver/controller.py` lines 259-308).
*   **Roku UPnP Discovery:** `13-discovery.md` uses Roku as a UPnP example, but there is no `roku` provider in the codebase.
*   **Metadata Locale:** `14-metadata.md` says the locale looks like `'en_EN'`. The code and config actually use standard formats like `en_US` or `de_DE` (`controllers/metadata.py` lines 250-253).
*   **Track Metadata Refresh:** `14-metadata.md` claims online metadata is "Always attempted if online metadata is enabled." The code returns immediately if the track is fresh (`< REFRESH_INTERVAL`) unless `force_refresh` is true (`metadata.py` lines 732-734).
*   **Lyrics Fallback Chain:** The doc implies a fixed LRCLIB then Genius order. The code iterates `self.providers` in list order after existing metadata/library checks (`metadata.py` lines 576-610).

### Missing Cross-Cutting Context
*   **Plugin Exclusivity in Streams:** The streams controller's `get_plugin_source_stream` also sets/clears `in_use_by` around streaming (`controllers/streams/controller.py` lines 1056-1102), extending plugin exclusivity beyond just the player controller's selection logic.
*   **Webserver Locale to Metadata:** On every WebSocket connection, the webserver parses the `Accept-Language` header and calls `set_default_preferred_language` (`webserver/controller.py` lines 507-510), tightly coupling client connections to metadata resolution.
*   **Dynamic API Surface:** Besides Party, `mass.register_api_command` is used heavily across `controllers/media/*`, `config`, and `remote_access`. The docs don't capture the scale of this dynamic registration.
*   **Ingress vs Main Site Auth:** The `auth_middleware` explicitly bypasses auth for ingress and for long prefix lists (`webserver/helpers/auth_middleware.py` lines 242-270), which complements the ingress section in doc 12.

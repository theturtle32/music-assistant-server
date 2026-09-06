# Independent Architecture Verification Report (GPT-5.4) v1.0

This report is an independent, code-driven verification of the generated architecture corpus in `docs/architecture/README.md` and `docs/architecture/00` through `15`. The server implementation under `music_assistant/` was treated as the source of truth. External model definitions in `music_assistant_models` were only assumed where the local server clearly depends on them.

## Core, Events, Config, and Provider Lifecycle

Reviewed docs: `README.md`, `00-overview.md`, `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`.

### Core Domain: Verified Accuracies

- The documented startup and shutdown ordering is materially correct: `ConfigController` is initialized first, provider manifests are loaded before storage/controller setup, seven core controllers are set up in parallel, API commands are registered before the webserver starts, builtin providers still load in safe mode, and shutdown closes controllers in the documented reverse order. Evidence: `music_assistant/mass.py:138-244`.
- The event bus description is accurate on the important mechanics: `signal_event` short-circuits while closing, enforces event-loop affinity, iterates over a snapshot of subscribers, dispatches async subscribers via `create_task`, and schedules sync subscribers with `call_soon_threadsafe`. Evidence: `music_assistant/mass.py:419-448`.
- The API-command registration flow is correctly described: `_register_api_commands()` scans the `MusicAssistant` hub, core controllers, the webserver, and the auth manager, while explicitly skipping properties to avoid lazy-init side effects. Evidence: `music_assistant/mass.py:767-796`.
- The provider-loading happy path is correctly represented: `_load_provider()` validates config, honors `depends_on`, dynamically imports the provider module, enforces a 30-second setup timeout, sets `provider.available = True`, signals `PROVIDERS_UPDATED`, and then invokes the music/player controller hooks. Evidence: `music_assistant/mass.py:889-964`.
- The manifest discovery flow is correctly described: manifest scanning skips hidden directories, skips `_`-prefixed providers unless `dev_mode` is enabled, loads manifests in parallel, and applies the HA add-on override for the `hass` provider. Evidence: `music_assistant/mass.py:966-1023`.
- The config encryption description is accurate at the server level: a server ID is created if missing, the first 32 bytes are used to derive a Fernet key, and the config-entry encrypt/decrypt callbacks are installed during config setup. Evidence: `music_assistant/controllers/config.py:148-165`.
- The save-debounce description is accurate: `ConfigController.save()` schedules `_async_save()` after `DEFAULT_SAVE_DELAY`, while `immediate=True` bypasses the delay. Evidence: `music_assistant/controllers/config.py:1289-1301`.
- The cache/storage overview is largely correct: the cache controller keeps a 500-entry memory cache, avoids persisting short-lived entries to SQLite when the remaining TTL is under 1800 seconds, and caps the cache DB size at 2048 MB. Evidence: `music_assistant/controllers/cache.py:40-57`, `music_assistant/controllers/cache.py:186-195`.

### Core Domain: Inaccuracies and Stale Info

- `00-overview.md` and `15-provider-lifecycle.md` overstate provider-load throttling. The docs say regular providers are loaded via `TaskManager(self, 2)` with a concurrency limit of 2, but `_load_providers()` calls `tg.create_task(...)`, and the semaphore is only honored by `create_task_with_limit(...)`, which is not used here. Evidence: `music_assistant/mass.py:882-887`, `music_assistant/helpers/util.py:1128-1151`.
- `02-configuration.md` says the default `Provider.update_config()` reloads only when changed entries have `requires_reload=True`. The actual default implementation reloads on any non-`log_level` `values/*` change, without checking the entry metadata. Evidence: `music_assistant/models/provider.py:66-96`.
- The safe-mode narrative is slightly inconsistent across the generated docs and CLI surface. The docs correctly say builtin providers still load in safe mode, but the CLI help text says "`core controllers only, no providers`", which is not how startup behaves. Evidence: `music_assistant/mass.py:199-209`, `music_assistant/__main__.py:71-75`.
- The provider-lifecycle docs omit an odd but real post-load behavior: after a successful `load_provider()`, the server iterates currently loaded-but-unavailable providers whose `depends_on` matches the newly loaded provider and calls `unload_provider()` on them instead of directly reloading them there. Evidence: `music_assistant/mass.py:707-712`.
- The data-directory discussion in `00-overview.md` is incomplete if read as a hard default. The entry point prefers `XDG_DATA_HOME/music-assistant` and `XDG_CACHE_HOME/music-assistant` when those environment variables are set, and only falls back to `~/.musicassistant` / `~/.musicassistant/.cache` otherwise. Evidence: `music_assistant/__main__.py:39-48`.
- The database PRAGMA table in `02-configuration.md` omits settings that are actually applied on connection setup, including `analysis_limit` and `journal_size_limit`. Evidence: `music_assistant/helpers/database.py:109-118`.
- `01-event-system.md` attributes only `api_cmd`, `api_authenticated`, and `api_required_role` to the decorator path correctly, but the broader registration discussion should not imply that `alias` comes from `@api_command`; `alias` is handled in registration/handler metadata, not by the decorator itself. Evidence: `music_assistant/helpers/api.py:364-380`, `music_assistant/controllers/config.py:160-165`.

### Core Domain: Missing Cross-Cutting Context

- The docs do not call out that `MASS_SAFE_MODE` is coerced with `bool(...)`, so any non-empty environment value, including `"0"`, enables safe mode. That matters operationally when startup behavior appears inconsistent with expected boolean parsing. Evidence: `music_assistant/__main__.py:224-229`.
- The docs do not mention that `ConfigController.close()` only forces a save when a debounce timer is still pending. If no timer exists, close returns immediately. Evidence: `music_assistant/controllers/config.py:189-195`.
- The onboarding flow is missing from the event/API lifecycle explanation: when onboarding is incomplete, `ConfigController.setup()` dynamically registers `config/onboard_complete` as an alias API command, independent of `_register_api_commands()`. Evidence: `music_assistant/controllers/config.py:160-165`.
- The provider lifecycle docs underplay that provider readiness is announced before all post-load work is complete. `_load_provider()` schedules `loaded_in_mass()` and `run_provider_discovery()` as a background task, then immediately clears `last_error`, signals `PROVIDERS_UPDATED`, updates the available-provider cache, and calls controller hooks. Evidence: `music_assistant/mass.py:947-964`.

## Players, Grouping, and Volume

Reviewed docs: `03-player-model.md`, `04-player-controller.md`, `05-protocol-linking.md`, `06-grouping.md`, `07-volume.md`.

### Players Domain: Verified Accuracies

- The docs correctly describe how non-protocol players are registered: `PLAYER_ADDED` is only emitted for non-`PROTOCOL` players, and queue registration is also skipped for protocol children. Evidence: `music_assistant/controllers/players/controller.py:1390-1397`.
- The controller does debounce queue-side state propagation exactly as described: non-protocol player updates schedule `player_queues.on_player_update(...)`, while `PLAYER_UPDATED` is only emitted for non-protocol players. Evidence: `music_assistant/controllers/players/controller.py:1560-1599`.
- The group-volume averaging model is correct: group volume is derived from powered members via `iter_group_members(..., only_powered=True, exclude_self=self.type != PlayerType.PLAYER)` and returns `None` when no effective member volume is available. Evidence: `music_assistant/models/player.py:840-870`.
- The docs are right that plugin volume callbacks run in addition to native volume handling. `_handle_cmd_volume_set()` first calls `plugin_source.on_volume(...)` when present and then still executes native/fake/delegated player-volume logic. Evidence: `music_assistant/controllers/players/controller.py:2915-2927`.
- The source-list explanation is mostly accurate for normal players: `Player.__final_source_list` always ensures the MA queue source exists and then appends plugin sources converted through `as_player_source()` when available. Evidence: `music_assistant/models/player.py:1721-1746`, `music_assistant/models/plugin.py:137-146`.

### Players Domain: Inaccuracies and Stale Info

- `04-player-controller.md` says the controller signals three player events "all excluding PROTOCOL players." That is only true for `PLAYER_UPDATED`. `PLAYER_OPTIONS_UPDATED` and `PLAYER_CONFIG_UPDATED` are emitted without a `PlayerType.PROTOCOL` guard whenever the relevant state changes. Evidence: `music_assistant/controllers/players/controller.py:1597-1619`.
- `04-player-controller.md` over-describes `register_or_update(player)` as if it follows the full registration path. In reality, the existing-player branch just replaces the object, calls `update_state()`, schedules `_schedule_update_all_players()`, and returns. It does not re-run full registration side effects. Evidence: `music_assistant/controllers/players/controller.py:1403-1415`.
- `03-player-model.md` labels `play()` as "always available," but the base `Player.play()` implementation is abstract and raises `NotImplementedError` unless a provider overrides it. Evidence: `music_assistant/models/player.py:393-395`.
- `07-volume.md` simplifies `group_volume_muted` too far. The implementation returns `None` when a powered group has a mix of muted and unmuted members, not `False`. Evidence: `music_assistant/models/player.py:874-908`.
- `11-plugin-system.md` and the player-model discussion miss a real exception in source-list assembly: protocol players return early from `__final_source_list` and therefore never receive appended plugin sources in their visible source list. Evidence: `music_assistant/models/player.py:1721-1725`.

### Players Domain: Missing Cross-Cutting Context

- The docs do not explain a subtle state-ordering edge case: `group_volume` and `group_volume_muted` read from `self.state.group_members` while a new `PlayerState` is being computed, so membership changes can transiently be evaluated against the previous snapshot. Evidence: `music_assistant/models/player.py:851-860`, `music_assistant/models/player.py:885-895`.
- The docs do not explain the divergence between displayed active source and control routing for plugins. `Player.__final_active_source` only checks `plugin_source.in_use_by == self.player_id`, while command routing uses `_get_active_plugin_source()` and also matches `player.active_source == plugin_source.id`. Evidence: `music_assistant/models/player.py:1948-1967`, `music_assistant/controllers/players/controller.py:1979-1987`.
- The generated docs do not tie player updates back to queue safety strongly enough. The queue-facing update hook is explicitly skipped for protocol children, which is one of the key reasons protocol wrappers do not create duplicate queue state machines. Evidence: `music_assistant/controllers/players/controller.py:1560-1568`.

## Media Library, Queues, and Streaming Pipeline

Reviewed docs: `08-media-library.md`, `09-player-queues.md`, `10-streaming-pipeline.md`.

### Media Domain: Verified Accuracies

- The queue start/play path is accurately described: `play_index()` creates a new session ID, restores resume positions for long-form media, retries up to five items, marks failed items unavailable, advances with `allow_repeat=False`, clears flow-mode log state, resets `queue.flow_mode`, and then calls `players.play_media(...)`. Evidence: `music_assistant/controllers/player_queues.py:1144-1205`.
- The next-item loader is accurately documented: `load_next_queue_item()` retries forward through the queue, stops after 10 failed candidates, and uses `_load_item(...)` with the default `is_start=False`. Evidence: `music_assistant/controllers/player_queues.py:1451-1489`.
- The flow-stream startup path is correctly documented: queue flow mode is enabled, a fresh `flow_mode_stream_log` is created, and smart crossfade is downgraded to standard crossfade when the streams core is running with a minimal buffer. Evidence: `music_assistant/controllers/streams/audio.py:1664-1689`.
- The HTTP streaming split is correct: queue-item streaming validates `session_id` on `/single/...`, while flow-mode routes are intentionally shaped around a continuous queue session rather than the same point-in-time item validation. Evidence: `music_assistant/controllers/streams/controller.py:294-303`, `music_assistant/controllers/streams/controller.py:375-384`.
- The playback-progress system is partly documented correctly: queue updates call `_handle_playback_progress_report(...)` from `_update_queue_from_player(...)`, and the code still uses `PLAYBACK_REPORT_INTERVAL_SECONDS` as one of the triggers. Evidence: `music_assistant/controllers/player_queues.py:2720-2726`.

### Media Domain: Inaccuracies and Stale Info

- `08-media-library.md` understates `get_unique_providers()`. It does deduplicate streaming domains, but it also filters provider instances through the current user's `provider_filter` when present. Evidence: `music_assistant/controllers/music.py:1610-1624`.
- `10-streaming-pipeline.md` describes provider selection as an optional per-player `provider_filter`, but the stream-resolution logic actually looks at the queue's user context and prefers that user's provider filter before widening fallback to other mappings/providers. Evidence: `music_assistant/controllers/streams/audio.py:188-231`.
- `09-player-queues.md` makes the progress-report trigger sound purely time-based. The implementation also reports progress when `state` or `current_item_id` changes, not only on the 30-second cadence. Evidence: `music_assistant/controllers/player_queues.py:2720-2726`.

### Media Domain: Missing Cross-Cutting Context

- The docs omit the queue/stream recovery path after a flow buffer finishes. `queue_buffer_completed()` waits for the player to go idle, confirms the original session is still active, then resumes playback automatically if new items were appended while the player was draining its buffered audio. Evidence: `music_assistant/controllers/player_queues.py:1616-1664`.
- The docs miss a useful race-condition guard between buffering and queue advancement. `_preload_streamdetails()` waits up to 120 seconds for the currently buffered item to become the actual `queue.current_item` before preloading and enqueueing the next item. Evidence: `music_assistant/controllers/player_queues.py:2193-2213`.
- The radio and long-form playback story is incomplete without the resume-position logic in `play_index()`. Podcasts and audiobooks can resume from `resume_position_ms` when an explicit seek was not supplied. Evidence: `music_assistant/controllers/player_queues.py:1151-1158`.

## Plugins, Webserver API, Discovery, and Metadata

Reviewed docs: `11-plugin-system.md`, `12-webserver-api.md`, `13-discovery.md`, `14-metadata.md`.

### Infra Domain: Verified Accuracies

- The plugin-source model is accurately described at a high level: `PluginSource` extends `PlayerSource`, carries audio/stream metadata and runtime callbacks, and `as_player_source()` strips it down to serializable fields for state export. Evidence: `music_assistant/models/plugin.py:21-146`.
- Plugin-source selection is correctly described on the major steps: if a source is already in use by another player, the other player is stopped first; a stream URL is generated; the plugin source is bound to the target player; and playback continues as `MediaType.PLUGIN_SOURCE`. Evidence: `music_assistant/controllers/players/controller.py:2298-2317`, `music_assistant/controllers/streams/controller.py:367-373`.
- The webserver route inventory is broadly accurate: `/ws`, `/api`, `/imageproxy`, `/preview`, auth routes, setup routes, and `/sendspin` are all mounted by the webserver controller. Evidence: `music_assistant/controllers/webserver/controller.py:271-309`.
- The JSON-RPC HTTP handler description is correct on authentication and execution flow: requests are rejected with 503 before users exist, bearer auth is enforced for authenticated commands, arguments are parsed with the command signature/type hints, and coroutine results are awaited before response serialization. Evidence: `music_assistant/controllers/webserver/controller.py:517-592`.
- The metadata/image-proxy overview is materially correct: metadata setup registers `/imageproxy` dynamically on the streams server, and `handle_imageproxy()` decodes double-encoded paths, delegates to `get_thumbnail()`, and returns long-lived cache headers with permissive CORS. Evidence: `music_assistant/controllers/metadata.py:223-239`, `music_assistant/controllers/metadata.py:496-535`.
- The discovery docs correctly describe replay and recurring discovery behavior: cached mDNS results are replayed to newly loaded providers, and periodic UPnP discovery is scheduled based on active subscriptions. Evidence: `music_assistant/controllers/discovery/controller.py:256-332`.
- The websocket transport description is accurate on its backpressure envelope: the connection uses a heartbeat of 30 seconds and a bounded pending-message queue of 512 messages. Evidence: `music_assistant/controllers/webserver/websocket_client.py:44-68`.

### Infra Domain: Inaccuracies and Stale Info

- `11-plugin-system.md` gets the source-selection ordering wrong. The code resolves the stream URL, sets `plugin_source.in_use_by`, and only then invokes `on_select()`. Evidence: `music_assistant/controllers/players/controller.py:2311-2315`.
- `11-plugin-system.md` describes plugin callbacks as plain `() -> None` style callables, but the actual type contracts are async `Awaitable[None]` callbacks, including parameterized callbacks such as `on_seek(int)` and `on_volume(int)`. Evidence: `music_assistant/models/plugin.py:81-135`.
- `11-plugin-system.md` says the player source list appends all non-passive plugin sources. The implementation appends every plugin source returned by `get_plugin_sources()` and does not filter on `passive`. Evidence: `music_assistant/models/player.py:1740-1745`.
- `11-plugin-system.md` documents plugin-stream URLs without the format suffix, but the actual route and generated URL are `/pluginsource/{plugin_source}/{player_id}.{fmt}`. Evidence: `music_assistant/controllers/streams/controller.py:299-303`, `music_assistant/controllers/streams/controller.py:367-373`.
- `12-webserver-api.md` overgeneralizes the HTTP response shape from the websocket transport. The HTTP `/api` endpoint returns `web.json_response(result)` for successful command execution, not a websocket-style `SuccessResultMessage` envelope. Evidence: `music_assistant/controllers/webserver/controller.py:577-585`.
- `14-metadata.md` says `/imageproxy` lives on the streams server, but the same handler is also mounted on the main webserver. Evidence: `music_assistant/controllers/metadata.py:223-239`, `music_assistant/controllers/webserver/controller.py:275-279`.

### Infra Domain: Missing Cross-Cutting Context

- The docs do not connect the dual `/imageproxy` mounts to `get_image_url()`. That method intentionally chooses `webserver.base_url` by default and switches to `streams.base_url` when `prefer_stream_server=True`, which is the architectural reason the same metadata proxy exists on both servers. Evidence: `music_assistant/controllers/metadata.py:436-460`.
- The docs do not explain the practical protocol difference between websocket and HTTP command transports. Websocket wraps results/errors in message envelopes, while HTTP returns raw JSON bodies for success and plain HTTP error responses for failures/auth problems. Evidence: `music_assistant/controllers/webserver/controller.py:517-592`, `music_assistant/controllers/webserver/websocket_client.py:44-68`.
- The plugin-system docs do not discuss that protocol players never expose plugin sources in `__final_source_list`, even though plugin audio can still be routed through player-control logic elsewhere. Evidence: `music_assistant/models/player.py:1721-1725`, `music_assistant/controllers/players/controller.py:2298-2317`.

## Overall Assessment

The generated architecture set is directionally strong and often correct on control flow, lifecycle ordering, and subsystem boundaries. The biggest factual issues are concentrated in concurrency and edge-behavior details rather than the primary happy paths:

- Provider-load concurrency is documented as limited to 2, but the current `_load_providers()` path does not actually use the semaphore-backed `TaskManager` limit. Evidence: `music_assistant/mass.py:882-887`, `music_assistant/helpers/util.py:1128-1151`.
- Provider config reload semantics are overstated in the docs; providers reload on any non-`log_level` value change, not only `requires_reload=True` entries. Evidence: `music_assistant/models/provider.py:66-96`.
- Protocol-player exclusions are described too broadly in the player docs; some config/options events still fire for protocol players. Evidence: `music_assistant/controllers/players/controller.py:1597-1619`.
- The HTTP API docs borrow too much websocket terminology and should distinguish transport envelopes explicitly. Evidence: `music_assistant/controllers/webserver/controller.py:577-585`, `music_assistant/controllers/webserver/websocket_client.py:44-68`.
- Several important cross-domain recovery behaviors are undocumented: safe-mode env coercion, background provider post-load tasks, queue resume after flow-buffer completion, and dual image-proxy base-URL selection. Evidence: `music_assistant/__main__.py:224-229`, `music_assistant/mass.py:947-964`, `music_assistant/controllers/player_queues.py:1616-1664`, `music_assistant/controllers/metadata.py:436-460`.

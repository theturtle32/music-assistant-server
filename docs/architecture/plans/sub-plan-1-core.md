# Sub-plan 1: Core Architecture

**Scope**: The foundation that everything else builds on — server lifecycle, event system, configuration/persistence, and provider lifecycle.

**Context**: This is the first sub-plan. There are no prior architecture docs to reconcile against.

## Deliverables

You will produce 4 markdown files under `docs/architecture/`. Create the directory if it doesn't exist.

### 1. `docs/architecture/00-overview.md` — High-Level Architecture

The bird's-eye view of the entire system. A developer reading this first should understand the shape of the codebase before diving into any subsystem.

**Must cover:**

- What Music Assistant is (async Python music library manager connecting streaming services and speakers, integrating with Home Assistant)
- The multi-repo ecosystem: server (this repo), `music-assistant-models` (shared data models, mashumaro serialization, orjson, `API_SCHEMA_VERSION`/`MIN_SCHEMA_VERSION` for client-server compat), `music-assistant-client` (async Python client mirroring server controllers), frontend, protocol libraries (`aioslimproto`, `aiosonos`, `cliairplay`, etc.)
- The `MusicAssistant` class in `music_assistant/mass.py` as the central hub — it owns all controllers, the event bus, the provider registry, task tracking, and HTTP sessions
- Component map: 10 core controllers (config, discovery, cache, tasks, streams, music, metadata, players, player_queues, webserver), their relationships, and what each is responsible for (one sentence each — details come in later docs)
- Startup lifecycle (from `__main__.py` through `MusicAssistant.start()`):
  1. Config controller setup first (sequential, alone)
  2. Discovery controller instantiation
  3. Provider manifest loading (`__load_provider_manifests` — scans `music_assistant/providers/*/manifest.json`)
  4. Storage setup
  5. Other core controllers instantiated
  6. Core controller manifests registered into `_provider_manifests` (for `CONFIGURABLE_CORE_CONTROLLERS`)
  7. Parallel `setup()` of 7 controllers via `asyncio.TaskGroup`
  8. Sequential `post_setup()` for each
  9. API command registration (`_register_api_commands`)
  10. Webserver setup (sequential, after controllers ready)
  11. Discovery controller setup
  12. Builtin providers loaded (awaited, fail = fatal) — `_load_builtin_providers`
  13. Regular providers loaded in background tasks (fail = non-fatal, auto-retry) — `_load_providers`
  14. State set to `CoreState.RUNNING`
- Shutdown lifecycle (`MusicAssistant.stop()`): state -> STOPPING, cancel tracked tasks, unload all providers, close controllers in reverse-ish order, close HTTP sessions, state -> STOPPED
- Safe mode: what loads (config, core controllers, builtin providers), what doesn't (regular providers), why it exists
- `dev_mode` detection (checks `PYTHONDEVMODE` env var or `.venv` directory existence) — controls whether `_demo_*` providers are loaded
- Task management primitives: `create_task` (tracked, auto-cancelled on stop, supports `task_id` dedup and `eager_start`), `call_later` (debounced timer with `task_id`)
- Thread safety: `verify_event_loop_thread` enforces that critical operations run on the event loop thread
- Data directories: `storage_path` (default `~/.musicassistant/`) for persistent data, `cache_path` for disposable cache

**Key source files:**
- `music_assistant/mass.py` — `MusicAssistant` class (1077 lines)
- `music_assistant/__main__.py` — CLI entry point, argument parsing, logging setup (271 lines)
- `music_assistant/constants.py` — all config keys, DB table names, defaults

### 2. `docs/architecture/01-event-system.md` — Event System

The pub/sub backbone that ties the system together.

**Must cover:**

- `EventType` enum — defined in `music_assistant_models.enums`, imported by the server. List the major categories of events (player updates, queue updates, provider updates, config changes, media item updates, core state). You do NOT need to list every single enum value — group them meaningfully.
- `MassEvent` dataclass — defined in `music_assistant_models.event`. Fields: `event` (EventType), `object_id` (optional str), `data` (Any). This is the envelope.
- `signal_event` method on `MusicAssistant`:
  - Must run on event loop thread (enforced by `verify_event_loop_thread`)
  - Suppressed when `self.closing` is True
  - Iterates `_subscribers` set, matches against event_filter and id_filter
  - Async callbacks: dispatched via `create_task` (so they don't block the signaler)
  - Sync callbacks: dispatched via `loop.call_soon_threadsafe`
  - Verbose logging at custom `VERBOSE_LOG_LEVEL` (5)
- `subscribe` method:
  - Accepts callback (sync or async), optional event_filter (single or tuple of EventType), optional id_filter (single or tuple of str — player_id, queue_id, uri)
  - Returns an unsubscribe callable
  - Subscribers stored in a set of `EventSubscriptionType` tuples
- `command_handlers` (the imperative counterpart): dict of `str -> APICommandHandler`, registered via `register_api_command` or the `@api_command` decorator. Commands are request-response (called by clients via JSON-RPC), events are fire-and-forget broadcast. Explain when each is appropriate.
- The `@api_command` decorator in `music_assistant/helpers/api.py` — how it marks methods with `api_cmd`, `api_authenticated`, `api_required_role` attributes that are picked up by `_register_api_commands`

**Key source files:**
- `music_assistant/mass.py` — `signal_event`, `subscribe`, `register_api_command`, `_register_api_commands` (lines ~419-796)
- `music_assistant/helpers/api.py` — `api_command` decorator, `APICommandHandler` dataclass
- `music_assistant_models` package (installed dependency, version 1.1.110) — `EventType`, `MassEvent`

**Research approach:** For `EventType`, look at the installed `music_assistant_models` package. You can find it via:
```
python -c "import music_assistant_models.enums; import inspect; print(inspect.getfile(music_assistant_models.enums))"
```
Or search for it in the venv's site-packages. The enum values are the authoritative source — do not guess from usage patterns alone.

### 3. `docs/architecture/02-configuration.md` — Configuration and Persistence

How settings are stored, loaded, and managed.

**Must cover:**

- `ConfigController` in `music_assistant/controllers/config.py` — the first controller setup during startup (before all others). It owns the JSON config file and provides the get/set interface for all other controllers.
- Config hierarchy:
  - **CoreConfig** — per-controller settings (one per configurable core controller, listed in `CONFIGURABLE_CORE_CONTROLLERS`: discovery, streams, webserver, players, metadata, cache, music, player_queues)
  - **ProviderConfig** — per-provider-instance settings (domain, instance_id, enabled, values, last_error)
  - **PlayerConfig** — per-player settings (player_id, provider, enabled, values with categories like "generic", "playback", "protocol_generic", "announcements", "player_controls")
  - All three types defined in `music_assistant_models.config_entries`
- `ConfigEntry` — the building block: key, type (ConfigEntryType enum), label, description, default_value, options, range, category, advanced, hidden, required, depends_on, requires_reload, multi_value
- The extensive reusable config entries in `music_assistant/constants.py` (CONF_ENTRY_FLOW_MODE, CONF_ENTRY_OUTPUT_CODEC, CONF_ENTRY_SAMPLE_RATES, etc.) — explain the pattern: providers compose their config from these shared entries plus provider-specific ones
- How config changes propagate: `update_config` on CoreController checks `requires_reload` and calls `reload` if needed (via `call_later` with 1s debounce). For providers, a similar pattern exists.
- Encryption: `ENCRYPT_SUFFIX` pattern for sensitive values (uses Fernet symmetric encryption)
- SQLite databases (explore `music_assistant/helpers/database.py`):
  - **Library DB** (`library.db` in storage_path) — media items, provider mappings, playlog, loudness measurements, smart fades analysis, genres
  - **Cache DB** (in cache_path) — ephemeral cached data
  - DB table constants defined in `music_assistant/constants.py` (DB_TABLE_*)
- `CacheController` in `music_assistant/controllers/cache.py` — how it wraps the cache DB

**Key source files:**
- `music_assistant/controllers/config.py` (2106 lines) — the main config controller
- `music_assistant/controllers/cache.py` — cache controller
- `music_assistant/helpers/database.py` — SQLite helpers
- `music_assistant/constants.py` — config keys (CONF_*), DB tables (DB_TABLE_*), reusable config entries (CONF_ENTRY_*)
- `music_assistant_models.config_entries` — CoreConfig, ProviderConfig, PlayerConfig, ConfigEntry, ConfigValueType

### 4. `docs/architecture/15-provider-lifecycle.md` — Provider Lifecycle

How providers are discovered, loaded, configured, and integrated into the running system.

**Must cover:**

- Provider taxonomy (from `ProviderType` enum in models):
  - **MUSIC** — sources of media (Spotify, filesystem, etc.)
  - **PLAYER** — speakers/renderers (Chromecast, AirPlay, DLNA, etc.)
  - **METADATA** — art, lyrics, biographies (TheAudioDB, MusicBrainz, etc.)
  - **PLUGIN** — extras like Spotify Connect, scrobblers, receivers
  - **CORE** — not a "real" provider type, used for core controllers' manifests
- `ProviderManifest` (from `music_assistant_models.provider`) — the `manifest.json` schema: domain, name, type, description, codeowners, requirements (pip packages), depends_on, multi_instance, builtin, allow_disable, mdns_discovery, upnp_discovery, stage (ProviderStage)
- Manifest discovery: `__load_provider_manifests` scans `music_assistant/providers/*/manifest.json` at startup, skips `_`-prefixed dirs unless `dev_mode`, loads in parallel via `TaskManager`
- The `Provider` base class in `music_assistant/models/provider.py`:
  - Constructor: receives `mass`, `manifest`, `config`, optional `supported_features`
  - Key lifecycle methods: `setup()` (called by the provider module's top-level `setup` function), `handle_async_init()`, `loaded_in_mass()`, `unload(is_removed)`
  - `available` flag — set True after successful load
  - Feature flags via `supported_features` property (set of `ProviderFeature`)
  - Discovery callbacks: `on_mdns_service_state_change`, `on_upnp_device_state_change`
- Provider subclasses in `music_assistant/models/`:
  - `MusicProvider` (music_provider.py) — adds media browsing, search, library sync, stream resolution
  - `PlayerProvider` (player_provider.py) — adds player discovery/registration, command handling
  - `MetadataProvider` (metadata_provider.py) — adds metadata resolution methods
  - `Plugin` (plugin.py) — PluginSource with callbacks (on_play, on_pause, on_volume, etc.)
- Loading flow (trace through `_load_provider` in mass.py):
  1. Unload existing instance if present
  2. Validate config
  3. Check manifest exists, check multi_instance constraint
  4. Check `depends_on` — if dependency not loaded, silently skip (will auto-retry when dependency loads)
  5. `load_provider_module` (from `helpers/util.py`) — dynamic import + pip install requirements
  6. Call module's `setup(mass, manifest, config)` with 30s timeout
  7. Call `handle_async_init()`
  8. Register in `_providers` dict, set `available = True`
  9. Post-load task: `loaded_in_mass()`, then `run_provider_discovery`
  10. Signal `EventType.PROVIDERS_UPDATED`
  11. Type-specific callbacks: `music.on_provider_loaded()` or `players.on_provider_loaded()`
- Builtin vs regular providers:
  - **Builtin** (`manifest.builtin = True`): loaded synchronously via TaskGroup, failure is fatal. Examples: sync_group, universal_group, hass (when running as add-on)
  - **Regular**: loaded as background tasks via `TaskManager(self, 2)` (concurrency limit 2), failure triggers auto-retry after 120s for `MusicAssistantError` subclasses
- Default providers: `DEFAULT_PROVIDERS` set in constants — providers auto-setup on first run (airplay, chromecast, dlna, sonos, bluesound, heos, party). Some require mDNS evidence before auto-setup (`require_mdns=True`)
- Unloading (`unload_provider`): unschedule music sync, notify player/music controllers, unload dependents recursively, unregister players (for PlayerProviders), call `provider.unload()`, remove from `_providers`, signal update
- Error handling: `last_error` persisted in config for UI display, `unload_provider_with_error` for runtime failures needing user action

**Key source files:**
- `music_assistant/mass.py` — `_load_provider`, `_load_builtin_providers`, `_load_providers`, `__load_provider_manifests`, `load_provider`, `unload_provider`, `load_provider_config`
- `music_assistant/models/provider.py` — `Provider` base class
- `music_assistant/models/music_provider.py`, `player_provider.py`, `metadata_provider.py`, `plugin.py` — subclasses
- `music_assistant/helpers/util.py` — `load_provider_module`
- `music_assistant/constants.py` — `DEFAULT_PROVIDERS`, `CONFIGURABLE_CORE_CONTROLLERS`
- Any `manifest.json` file under `music_assistant/providers/` — examine a few to understand the schema in practice

## Writing Principles

- **Cite code, not assumptions**: Every claim must be backed by specific file + method/class name. Line numbers go stale, so prefer method names.
- **Explain the "why"**: Not just what the code does, but why it is structured that way. Use git history (`git log --oneline -20 music_assistant/mass.py`, etc.) and PR context where available.
- **Flag known gaps honestly**: Where the architecture has rough edges, note them as known limitations rather than proposing fixes.
- **Keep it skimmable**: Use Mermaid diagrams for flows, tables for comparisons, keep code snippets short.
- **Human voice**: Written to be presentable to project maintainers. No AI filler, no over-explanation of obvious things.
- **Docstring format**: When showing example code, use Sphinx-style docstrings with `:param:` syntax (this is the project convention).

## Exploration Strategy

1. **Start with `mass.py`** — read it end-to-end. This is the nucleus. Every other file in scope is referenced from here.
2. **Read `__main__.py`** — understand the CLI entry point, how `MusicAssistant` is instantiated, logging setup.
3. **Read `models/core_controller.py`** — the base class for all controllers. Small file (~110 lines), understand the `setup`/`post_setup`/`close`/`reload`/`update_config` lifecycle.
4. **Read `models/provider.py`** — the base class for all providers (~218 lines). Then skim the subclasses (`music_provider.py`, `player_provider.py`, `metadata_provider.py`, `plugin.py`) for their additional interface methods — you don't need deep understanding yet, just the shape.
5. **Read `controllers/config.py`** — large file (~2106 lines). Focus on: class structure, `setup()`, `get_core_config`, `get_provider_config`, `get_player_config`, `save_provider_config`, `create_builtin_provider_config`, the JSON file I/O, encryption.
6. **Read `controllers/cache.py`** — understand the cache DB interface.
7. **Read `helpers/database.py`** — understand the SQLite abstraction layer.
8. **Read `helpers/api.py`** — understand `@api_command` decorator and `APICommandHandler`.
9. **Read `constants.py`** — you'll have already seen this during earlier reads, but do a focused scan of the config key sections, DB table sections, and `CONFIGURABLE_CORE_CONTROLLERS` / `DEFAULT_PROVIDERS`.
10. **Examine `music_assistant_models`** — find EventType and MassEvent definitions. Check the installed package (look in the Python environment's site-packages, or use `python -c "import ..."` to locate files).
11. **Examine 2-3 provider manifest.json files** — e.g., `providers/spotify/manifest.json`, `providers/chromecast/manifest.json`, `providers/sync_group/manifest.json` — to show concrete examples of the manifest schema.
12. **Git history**: Run `git log --oneline -30 music_assistant/mass.py` to understand recent lifecycle refactors. Look for commits mentioning "safe mode", "startup", "provider loading".

## Output Format

Each deliverable should be a standalone markdown document that:
- Opens with a one-paragraph summary of what the subsystem does and why it matters
- Uses `##` headers for major sections
- Includes at least one Mermaid diagram where a flow or relationship is complex enough to warrant it (startup lifecycle is the obvious candidate for `00-overview.md`)
- Uses tables for comparisons (e.g., builtin vs regular providers, sync vs async event callbacks)
- Keeps code snippets to essential signatures — don't paste entire functions
- Ends with a "Key Files" section listing the source files covered, so future readers know where to look
- Cross-references other architecture docs where relevant (e.g., `00-overview.md` should mention that the event system is covered in detail in `01-event-system.md`)

## What NOT to Cover

These topics belong to later sub-plans. Mention them only in passing with forward references:

- Player model internals, PlayerController command routing (Sub-plan 2)
- Grouping, volume control (Sub-plan 3)
- Media library, queue management, streaming pipeline (Sub-plan 4)
- Plugin system details, webserver internals, discovery internals, metadata enrichment (Sub-plan 5)

If you find yourself writing more than 2-3 sentences about any of these topics, stop and add a forward reference instead.

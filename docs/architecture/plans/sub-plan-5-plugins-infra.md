# Sub-plan 5: Plugins, Webserver, Discovery, and Metadata

**Scope**: Plugin system, webserver/API, discovery, and metadata enrichment. This sub-plan writes the last 4 content docs and reconciles with all prior output. The final convergence review is a separate Sub-plan 6.

**Context**: Sub-plans 1-4 are complete. Twelve architecture docs exist under `docs/architecture/`: `00-overview.md` through `10-streaming-pipeline.md` plus `15-provider-lifecycle.md`. This sub-plan adds the final 4 content documents.

**Model**: 1M context (must write 4 new docs AND read all 12 prior documents for reconciliation; the plugin system touches players, groups, volume, and streaming simultaneously; webserver/API touches events, config, and command routing).

## Deliverables

You will produce 4 markdown files under `docs/architecture/`.

### 1. `docs/architecture/11-plugin-system.md` — Plugin System

How external integrations bridge into the Music Assistant player model.

**Must cover:**

- **`PluginSource`** dataclass (`music_assistant/models/plugin.py`, ~185 lines): A `PlayerSource` subclass that adds:
  - `audio_format` — PCM format for the audio stream (default: 16-bit 44.1kHz stereo)
  - `metadata` — `StreamMetadata` for current playing info (title, artist, album, image, elapsed time)
  - `stream_type` — `StreamType.CUSTOM` (provider supplies raw audio) or URL-based
  - `path` — source path when stream_type is not CUSTOM
  - `in_use_by` — player_id currently using this source (single player, not groups — document this limitation)
  - Callbacks: `on_play`, `on_pause`, `on_next`, `on_previous`, `on_seek`, `on_volume`, `on_select`
  - `as_player_source()` — strips non-serializable callbacks for API exposure

- **`PluginProvider`** base class: extends `Provider`, adds `get_source()` (returns `PluginSource`), `get_audio_stream(player_id)` (returns raw audio bytes generator for CUSTOM streams), `resolve_image()`.

- **Plugin taxonomy** — two categories:
  - **Receiver plugins** (audio source providers): Spotify Connect, AirPlay Receiver, AriaCast Receiver, VBAN Receiver. These provide audio streams from external apps and bridge playback control via callbacks.
  - **Scrobbler plugins**: Last.fm, ListenBrainz, Subsonic. These listen for playback events and report plays to external services. No audio source.
  - **Party plugin**: Guest access with QR codes, queue management with rate limiting. Neither a receiver nor scrobbler — it's a UI/access plugin.

- **How plugins integrate with players**: When a plugin's source is selected for a player, the plugin's `PluginSource` becomes the player's `active_source`. The streams controller uses `StreamType.CUSTOM` to call `plugin.get_audio_stream(player_id)` for the audio. Playback commands on the player trigger the corresponding `PluginSource` callbacks (`on_play`, `on_pause`, etc.) — see `_handle_cmd_play`, `_handle_cmd_pause` in the player controller.

- **Spotify Connect as exemplar** (`music_assistant/providers/spotify_connect/`, ARCHITECTURE.md exists):
  - librespot subprocess — Spotify's reverse-engineered audio protocol
  - `events.py` webservice — receives session events, metadata updates, volume changes from librespot
  - Multi-instance support — one librespot per MA player, with dynamic `PluginSource` per player
  - Credential flow — uses stored Spotify credentials or connects via zeroconf
  - The existing `spotify_connect/ARCHITECTURE.md` is detailed — verify against code, incorporate accurate content

- **`in_use_by` semantics**: Always a physical player ID, not a group ID. When a group is playing from a plugin source, only the group player ID is tracked — individual child players don't have `in_use_by` pointing to them. This means plugin callbacks (especially `on_volume`) only fire for commands to the group player, not for individual member volume changes. This gap is documented in `07-volume.md` — cross-reference it.

- **Plugin source registration**: How plugins register their `PluginSource` with the player controller via `register_plugin_source` / `get_plugin_sources` / `get_plugin_source`. How `_get_active_plugin_source` resolves which plugin is active for a player.

**Key source files:**
- `music_assistant/models/plugin.py` (~185 lines) — `PluginSource`, `PluginProvider`
- `music_assistant/providers/spotify_connect/` — `__init__.py` (~860 lines), `events.py`, `ARCHITECTURE.md`
- `music_assistant/providers/airplay_receiver/`, `ariacast_receiver/`, `vban_receiver/` — receiver plugins
- `music_assistant/providers/lastfm_scrobble/`, `listenbrainz_scrobble/`, `subsonic_scrobble/` — scrobbler plugins
- `music_assistant/providers/party/` — party plugin
- `music_assistant/controllers/players/controller.py` — `register_plugin_source`, `get_plugin_sources`, `_get_active_plugin_source`

### 2. `docs/architecture/12-webserver-api.md` — Webserver and API

The JSON-RPC command model, WebSocket connections, authentication, and remote access.

**Must cover:**

- **`WebserverController`** (`controllers/webserver/controller.py`, ~1063 lines): The main webserver on port 8095 (default). Serves: the Vue.js frontend PWA, WebSocket API (`/ws`), HTTP/JSON-RPC API (`/api`), auth routes (`/login`, `/auth/*`, `/setup`), API docs (`/api-docs`), image proxy, audio preview.

- **JSON-RPC command model**: `CommandMessage` (from models) → dispatched via `command_handlers` dict on `MusicAssistant`. The `@api_command` decorator (from `helpers/api.py`) registers methods with a command path (e.g., `"players/all"`, `"player_queues/play_media"`). `parse_arguments` introspects type hints to validate and coerce parameters. `APICommandHandler` dataclass holds the handler, authentication requirement, required role, and parameter metadata.

- **WebSocket** (`websocket_client.py`, ~479 lines): `WebsocketClientHandler` — manages a single WebSocket connection. Authentication via first message (token or HA ingress auto-auth). Event subscription model: client subscribes to event types, receives `MassEvent` broadcasts. Command execution: client sends `CommandMessage`, server dispatches via `command_handlers`, returns `SuccessResultMessage` or `ErrorResultMessage`. Writer queue with `MAX_PENDING_MSG` (512) backpressure.

- **Authentication** (`auth.py`, ~1833 lines): `AuthenticationManager` with its own SQLite database (`auth.db`):
  - **Users**: `UserRole` (ADMIN, USER, GUEST), `User` dataclass
  - **Auth providers**: `BuiltinLoginProvider` (bcrypt password hashing), `HomeAssistantOAuthProvider` (OAuth2 flow when HA provider is configured)
  - **Tokens**: Short-lived (30 days, auto-renewing) and long-lived (10 years). JWT-based via `JWTHelper`.
  - **Join codes**: 6-character codes (no ambiguous chars) for QR/link-based login (used by party plugin). Expiration, max uses.
  - **Context variables**: `get_current_user()`, `get_current_token()` — thread-local via `ContextVar` for request-scoped auth state

- **Remote access** (`remote_access/`): WebRTC-based remote connectivity via `RemoteAccessManager`. Uses a gateway service. Allows external access without port forwarding.

- **Home Assistant integration**: Ingress support (port 8094), auto-authentication for HA users, supervisor announcement for add-on discovery.

- **The existing `webserver/README.md`** is thorough — verify against code, incorporate accurate content.

**Key source files:**
- `music_assistant/controllers/webserver/controller.py` (~1063 lines)
- `music_assistant/controllers/webserver/auth.py` (~1833 lines)
- `music_assistant/controllers/webserver/websocket_client.py` (~479 lines)
- `music_assistant/controllers/webserver/api_docs.py` — OpenAPI spec generation
- `music_assistant/controllers/webserver/sendspin_proxy.py` — Sendspin WebSocket proxy
- `music_assistant/controllers/webserver/helpers/` — auth middleware, auth providers, SSL
- `music_assistant/controllers/webserver/remote_access/` — WebRTC remote access
- `music_assistant/controllers/webserver/README.md` — existing detailed documentation
- `music_assistant/helpers/api.py` — `@api_command`, `APICommandHandler`, `parse_arguments`

### 3. `docs/architecture/13-discovery.md` — Network Discovery

How devices and services are found on the local network.

**Must cover:**

- **`DiscoveryController`** (`controllers/discovery/controller.py`, ~417 lines): Owns the shared `AsyncZeroconf` instance. Manages mDNS browsing and SSDP/UPnP search cycles.

- **mDNS/Zeroconf**: Single shared browser aggregated from all provider manifests' `mdns_discovery` fields. When a service is found, the controller routes the callback to the matching provider via `on_mdns_service_state_change`. Replay mechanism: when a provider loads, cached mDNS results are replayed so the provider doesn't need to wait for the next announcement.

- **SSDP/UPnP**: Periodic search cycles (`UPNP_DISCOVERY_INTERVAL` = 300s). Uses `async_upnp_client` (lazy imported). Fans out results to providers via `on_upnp_service_discovered`.

- **Interface selection**: Configurable via `CONF_ZEROCONF_INTERFACES` — default interface or all interfaces. Important for multi-homed hosts.

- **Server advertisement**: Registers `_mass._tcp.local.` Zeroconf service for the MA server itself.

- **Provider integration**: Providers declare discovery subscriptions in `manifest.json` (`mdns_discovery`, `upnp_discovery`). They implement callbacks in their provider class. Player providers can also use `discover_players()` for provider-specific discovery (manual IPs, controller-side refresh).

- **`run_provider_discovery`** (on `MusicAssistant`): Called after provider loads — triggers both shared discovery replay and provider-specific discovery.

- **The existing `discovery/README.md`** is concise — verify and expand.

**Key source files:**
- `music_assistant/controllers/discovery/controller.py` (~417 lines)
- `music_assistant/controllers/discovery/README.md` — existing documentation
- Provider manifests — `mdns_discovery` and `upnp_discovery` fields

### 4. `docs/architecture/14-metadata.md` — Metadata Enrichment

How artwork, lyrics, and biographies are fetched and managed.

**Must cover:**

- **`MetaDataController`** (`controllers/metadata.py`, ~1122 lines): Orchestrates metadata enrichment from all metadata providers. Key methods: `get_artist_metadata`, `get_album_metadata`, `get_track_metadata`, `get_playlist_metadata`. Also handles: image proxy, thumbnail caching, genre resolution.

- **Metadata providers**: `MetadataProvider` ABC (`models/metadata_provider.py`) — defines interface methods for resolving metadata. Current providers:
  - **TheAudioDB** — artist images, album art, biographies
  - **MusicBrainz** — authoritative external IDs, release matching
  - **Fanart.tv** — high-quality fan art, logos, banners
  - **Genius Lyrics** / **LRClib** — lyrics (plain text and synced/LRC format)

- **Provider priority**: How the controller iterates metadata providers for each type of enrichment. Music providers are checked first (they may supply their own artwork), then dedicated metadata providers.

- **Image proxy**: `get_image_url` / `get_image_thumb_url` — generates proxy URLs that route through the webserver. `_handle_imageproxy` serves images, caching thumbnails in `DB_TABLE_THUMBS` (SQLite). Image providers include local provider paths, URLs, and embedded artwork extraction.

- **Enrichment scheduling**: Metadata enrichment runs as background tasks via the TasksController. Scheduled enrichment passes scan library items that lack metadata.

- **Genre handling**: `GenreController` (in `controllers/media/genres.py`) plus genre mapping from `DEFAULT_GENRE_MAPPING` in constants. Genre aliases, icon mappings.

**Key source files:**
- `music_assistant/controllers/metadata.py` (~1122 lines)
- `music_assistant/models/metadata_provider.py` — `MetadataProvider` ABC
- `music_assistant/providers/theaudiodb/`, `musicbrainz/`, `fanarttv/`, `genius_lyrics/`, `lrclib/` — metadata providers
- `music_assistant/helpers/images.py` — image processing utilities

## Writing Principles

Same as prior sub-plans:
- Cite code, not assumptions. Every claim backed by file + method/class name.
- Explain the "why", not just the "what".
- Flag known gaps honestly.
- Keep it skimmable: Mermaid diagrams, tables, short code snippets.
- Human voice, no AI filler.

## Exploration Strategy

1. **Read `models/plugin.py`** — small file, the foundation. Understand `PluginSource` and `PluginProvider`.
2. **Read `providers/spotify_connect/__init__.py`** and `ARCHITECTURE.md` — the exemplar plugin. Understand librespot integration, event handling, PluginSource lifecycle.
3. **Skim 1-2 other plugin providers** (e.g., `airplay_receiver`, `lastfm_scrobble`) to see the pattern variation.
4. **Read `controllers/webserver/controller.py`** — the webserver. Focus on setup, route registration, WebSocket handling, JSON-RPC dispatch.
5. **Read `controllers/webserver/auth.py`** — authentication. Focus on user management, token lifecycle, auth providers, join codes.
6. **Read `controllers/webserver/websocket_client.py`** — WebSocket protocol. Focus on message handling, event subscription, backpressure.
7. **Read `controllers/webserver/README.md`** — existing thorough documentation. Verify against code.
8. **Read `controllers/discovery/controller.py`** — discovery. Focus on setup, mDNS browser, SSDP cycles, provider integration, replay.
9. **Read `controllers/discovery/README.md`** — existing documentation.
10. **Read `controllers/metadata.py`** — metadata enrichment. Focus on `get_*_metadata` methods, image proxy, provider iteration.
11. **Skim `models/metadata_provider.py`** — the MetadataProvider ABC.
12. **Read relevant parts of `controllers/players/controller.py`** — `register_plugin_source`, `get_plugin_sources`, `_get_active_plugin_source`, how plugin callbacks are invoked in command handlers.
13. **Git history**: `git log --oneline -15` on key files for recent changes.

## Reconciliation with Sub-plan 1-4

### Step 1 — Before exploring (structural vocabulary only)

Skim headings/terms from all 12 prior docs.

### Step 2 — After writing your own docs

Read all 12 prior documents in full. The plugin system is especially likely to reveal gaps in prior docs:

- **`07-volume.md`**: Describes the plugin volume feedback loop — does the plugin system doc's description of `PluginSource.on_volume` and `in_use_by` contradict or refine anything there?
- **`04-player-controller.md`**: Describes `select_source` — does the plugin doc's description of how plugins register as active sources add nuance?
- **`01-event-system.md`**: Describes the event bus — does the webserver doc reveal that some communication patterns (like JSON-RPC commands) bypass events entirely?
- **`09-player-queues.md`**: Describes the queue as "usual active source" — does the plugin doc clarify the alternative (plugin as active source)?
- **`10-streaming-pipeline.md`**: Does the plugin doc's description of `StreamType.CUSTOM` and direct audio streaming match what the pipeline doc says about plugin sources bypassing `AudioBuffer`?
- **`00-overview.md`**: Does the component map adequately introduce all 4 subsystems covered here?
- **`15-provider-lifecycle.md`**: Does it mention metadata providers and their enrichment role?

### Step 3 — Bidirectional revision

Fix errors in both directions. If the webserver doc reveals details about the JSON-RPC protocol that the event system doc should reference, add cross-references.

### Step 4 — Cascade check

Verify all revisions are internally consistent across all 12 prior docs plus the 4 new ones.

## What NOT to Cover (deferred to Sub-plan 6)

- **Final convergence review**: Sub-plan 6 will read all 16 documents end-to-end as a unified corpus, check terminology consistency, cross-reference completeness, contradictions, proportional depth, and produce `docs/architecture/README.md`.
- Do NOT produce `README.md` in this sub-plan.

## Output Format

Same format as prior sub-plans:
- One-paragraph summary opening each document
- `##` headers for major sections
- At least one Mermaid diagram per document (plugin integration flow, WebSocket message sequence, discovery flow, metadata enrichment pipeline)
- Tables for comparisons (plugin types, auth providers, metadata provider capabilities)
- Short code snippets for essential signatures
- "Key Files" section at the end
- Cross-references to other architecture docs

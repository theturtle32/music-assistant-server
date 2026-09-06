# Sub-plan 4: Media, Queues, and Streaming

**Scope**: The music library, media types, player queues, and the audio streaming pipeline.

**Context**: Sub-plans 1-3 are complete. Nine architecture docs exist under `docs/architecture/`: `00-overview.md` through `07-volume.md` plus `15-provider-lifecycle.md`. This sub-plan covers the media and streaming layer and reconciles with all prior docs.

**Model**: 200k context (mostly self-contained subsystems; the streams controller has thorough existing docs to verify against; reconciliation with prior docs is moderate).

## Deliverables

You will produce 3 markdown files under `docs/architecture/`.

### 1. `docs/architecture/08-media-library.md` — Music Controller and Media Library

The unified media library that aggregates content from all music providers.

**Must cover:**

- **`MusicController`** (`music_assistant/controllers/music.py`, ~3217 lines): The orchestrator for all media data. Has 8 sub-controllers for each media type:
  - `artists` → `ArtistsController`
  - `albums` → `AlbumsController`
  - `tracks` → `TracksController`
  - `radio` → `RadioController`
  - `playlists` → `PlaylistController`
  - `audiobooks` → `AudiobooksController`
  - `podcasts` → `PodcastsController`
  - `genres` → `GenreController`

  Each sub-controller lives in `music_assistant/controllers/media/` and inherits from `MediaControllerBase` in `base.py`.

- **`MediaControllerBase`** (`controllers/media/base.py`, ~1191 lines): The ABC for all media type controllers. Key methods: `get`, `get_library_item`, `get_provider_item`, `add_item_to_library`, `remove_item_from_library`, `set_favorite`, `browse`, and the library sync machinery. Understand the general pattern — media items are fetched from providers, matched against existing library items, and stored in SQLite.

- **`MusicProvider`** ABC (`models/music_provider.py`, ~1459 lines): The interface music providers implement. Key methods: `search`, `get_library_*` (for each media type), `get_*` (for individual items), `get_stream_details`, `get_audio_stream`, `library_add`, `library_remove`, `browse`. The `is_streaming_provider` flag distinguishes streaming services (Spotify, Tidal) from local sources (filesystem).

- **Library sync**: How the MusicController synchronizes provider catalogs into the library. The sync process: iterates provider's library items, matches against existing items (via `compare_media_item` in `helpers/compare.py`), updates/inserts into SQLite. Scheduled via the TasksController. The `_sync_lock` prevents concurrent syncs. Provider mappings (`DB_TABLE_PROVIDER_MAPPINGS`) track which library item came from which provider.

- **URI system**: How `uri://provider/item_id` URIs work. The `parse_uri` function, `get_item_by_uri`. URIs are the universal identifier for media items across the system.

- **Search**: `search()` aggregates results from all providers concurrently. `search_library()` searches only the SQLite database. The search aggregation pattern.

- **Provider orchestration**: How the MusicController dispatches to the correct provider when fetching items, how it handles multi-provider items (same track available from Spotify and Tidal), and how `get_unique_providers` tracks provider coverage.

- **SQLite tables**: The library database structure — `DB_TABLE_ARTISTS`, `DB_TABLE_ALBUMS`, `DB_TABLE_TRACKS`, `DB_TABLE_PLAYLISTS`, `DB_TABLE_RADIOS`, `DB_TABLE_AUDIOBOOKS`, `DB_TABLE_PODCASTS`, `DB_TABLE_GENRES`, plus junction tables (`DB_TABLE_ALBUM_TRACKS`, `DB_TABLE_TRACK_ARTISTS`, `DB_TABLE_ALBUM_ARTISTS`), and support tables (`DB_TABLE_PROVIDER_MAPPINGS`, `DB_TABLE_PLAYLOG`, `DB_TABLE_LOUDNESS_MEASUREMENTS`, `DB_TABLE_SMART_FADES_ANALYSIS`).

**Key source files:**
- `music_assistant/controllers/music.py` (~3217 lines)
- `music_assistant/controllers/media/base.py` (~1191 lines) — `MediaControllerBase`
- `music_assistant/controllers/media/tracks.py`, `artists.py`, `albums.py`, etc. — type-specific sub-controllers
- `music_assistant/models/music_provider.py` (~1459 lines) — `MusicProvider` ABC
- `music_assistant/helpers/compare.py` — media item comparison and matching
- `music_assistant/helpers/uri.py` — URI parsing

### 2. `docs/architecture/09-player-queues.md` — Player Queue Management

How media items are enqueued, ordered, and played back.

**Must cover:**

- **`PlayerQueuesController`** (`controllers/player_queues.py`, ~3204 lines): Manages all player queues. Each player has an associated `PlayerQueue` instance stored in `_queues` dict. Queue items in `_queue_items` dict.

- **`PlayerQueue` dataclass** (from `music_assistant_models.player_queue`): The queue state — `queue_id`, `active`, `state` (PlaybackState), `current_index`, `index_in_buffer`, `current_item`, `next_item`, `elapsed_time`, `shuffle_enabled`, `repeat_mode`, `crossfade_enabled`, `flow_mode_enforced`, `radio_mode`.

- **`QueueItem`** (from `music_assistant_models.queue_item`): Individual queue entries — `queue_item_id`, `queue_id`, `name`, `duration`, `media_item` (the resolved media), `streamdetails` (filled when playback starts), `extra_attributes`.

- **`play_media`**: The main entry point for playing media. Accepts `MediaItemType`, `ItemMapping`, URI string, or a list. Options: `QueueOption` (PLAY, REPLACE, NEXT, ADD, etc.), `radio_mode`. Resolves media items, creates `QueueItem`s, loads them into the queue, starts playback.

- **Queue loading** (`load`): Inserts items at a given index, optionally keeps remaining items, handles shuffle state.

- **Playback flow** — `play_index`:
  1. Loads the queue item via `_load_item` (fetches `StreamDetails`, creates `AudioBuffer` with `wait_ready=True`)
  2. Creates `PlayerMedia` via `player_media_from_queue_item`
  3. Dispatches play command to player via `self.mass.players.cmd_play` (which routes through the player controller)
  4. Pre-fills next track buffer via `_prepare_next_audio_buffer` (~30-60s before current track ends)

- **`_load_item`**: Fetches `StreamDetails` from the audio sub-controller, creates an `AudioBuffer` that starts filling immediately, waits for the buffer to be ready (enough data buffered).

- **`_prepare_next_audio_buffer`**: Pre-warms the buffer for the next track to ensure seamless transitions. Called proactively based on remaining time.

- **`load_next_queue_item`**: Called by the streams controller when the current stream is about to end. Returns the next `QueueItem`, advancing the queue index.

- **Queue as "the usual active source"**: The queue is the most common `active_source` for a player, but not the only one — plugins can be the active source too (forward reference to Sub-plan 5). The `active_source` on a player is the queue_id when the queue is active.

- **Playback controls**: `play`, `pause`, `resume` (with optional fade_in), `next`, `previous`, `seek`, `play_pause`. How these interact with the player controller (using `IN_QUEUE_COMMAND` ContextVar to prevent circular calls).

- **Shuffle and repeat**: How shuffle mode reorders items, how repeat modes (OFF, ONE, ALL) affect next/previous behavior.

- **Radio mode**: When enabled, automatically appends similar tracks when the queue is about to run out. Uses music provider recommendations.

- **Playback progress reporting**: `MediaItemPlaybackProgressReport` sent at `PLAYBACK_REPORT_INTERVAL_SECONDS` (30s). Updates the playlog.

- **`_transitioning_players`**: Set of player_ids currently between tracks — prevents duplicate next-track commands during transitions.

**Key source files:**
- `music_assistant/controllers/player_queues.py` (~3204 lines)
- `music_assistant_models.player_queue` — `PlayerQueue` dataclass
- `music_assistant_models.queue_item` — `QueueItem` dataclass

### 3. `docs/architecture/10-streaming-pipeline.md` — Audio Streaming Pipeline

The end-to-end audio path from music provider to player.

**Must cover:**

- **Architecture overview**: The pipeline stages:
  ```
  Music Provider → get_media_stream() → FFmpeg decode to raw PCM
    → AudioBuffer (raw PCM storage, analyze callbacks)
    → buffer.get_stream() → Optional: FFmpeg (volume normalization, speed, fade-in)
    → Optional: Smart Fades (crossfade mixing)
    → FFmpeg (encode to output format with player-specific DSP)
    → HTTP Response / Direct PCM stream
  ```

- **Network architecture**: The streams controller runs a separate HTTP-only webserver on port 8097 (default). No SSL, no auth — stream URLs use session IDs for validation. Why: embedded audio players have limited resources, audio is internal-network only.

- **`StreamsController`** (`controllers/streams/controller.py`, ~1140 lines): The HTTP server and public API. Key methods: `serve_queue_item_stream`, `serve_queue_flow_stream`, `serve_announcement`, `register_dynamic_route`. Manages the `Webserver` instance for audio streaming.

- **`StreamsAudio`** (`controllers/streams/audio.py`, ~2085 lines): The audio processing engine, accessible as `self.audio` on `StreamsController`. Key methods:
  - `get_stream_details` — resolves stream details for a queue item, determines source format, loudness, and normalization mode
  - `get_media_stream` — acquires raw PCM audio from the provider (calls provider's `get_audio_stream` or handles HTTP/file sources), decodes via FFmpeg
  - `get_queue_item_stream` — streams a single queue item with optional filters (volume normalization, speed adjustment, fade-in)
  - `get_queue_item_stream_with_smartfade` — streams with smart crossfade to the next track
  - `get_queue_flow_stream` — continuous flow stream of all queue tracks, yielding 1-second PCM chunks

- **`AudioBuffer`** (`controllers/streams/audio_buffer.py`, ~645 lines): The PCM buffer.
  - **Two modes**: `SEEKABLE` (tracks — deque of 1-second chunks, configurable max size) and `ROLLING` (radio — short 15-second FIFO)
  - **Buffer sizes**: `MINIMAL` (60s), `BALANCED` (300s), `MAXIMUM` (1200s) — auto-selected based on system memory
  - **Pre-initialization**: Buffers fill before players request streams (created in `_load_item`)
  - **Seek support**: Forward seeks within 20s wait for producer; larger seeks re-fetch from provider
  - **Analyze callbacks** (`ChunkCallback`): Observers that receive PCM data as it flows in — used for loudness measurement and beat detection
  - **Error handling**: Producer errors captured and surfaced when consumers read past buffered data

- **Stream entry points**:
  - **HTTP endpoints** (`serve_queue_item_stream`, `serve_queue_flow_stream`): For players consuming HTTP streams (Chromecast, DLNA, Sonos). Response includes DLNA-compatible headers, optional ICY metadata, HTTP profile selection (chunked, no content-length, forced content-length).
  - **Direct PCM** (`get_stream`): For providers that consume raw PCM directly (AirPlay, Sendspin)

- **Volume normalization**: Three modes — `measurement_based` (uses pre-measured EBU R128 loudness), `fallback_dynamic` (falls back to measurement if available, otherwise dynamic analysis), `fixed_gain` (constant dB adjustment). Target level configurable. Applied via FFmpeg `loudnorm` filter.

- **Smart fades system** (`controllers/streams/smart_fades/`):
  - **Analyzer** (`analyzer.py`): Beat detection using librosa (runs in background thread). Collects first 45s (intro) and last 45s (outro) of each track. Results cached in `DB_TABLE_SMART_FADES_ANALYSIS`.
  - **Fades** (`fades.py`): Fade curve generation for crossfade transitions.
  - **Mixer** (`mixer.py`): Crossfade mixing — blends outgoing track's outro with incoming track's intro.
  - Two modes: `SMART_CROSSFADE` (beat-matched transitions) and `STANDARD_CROSSFADE` (fixed-duration overlap with configurable duration).

- **DSP chain**: Per-player DSP configuration. `get_player_filter_params` generates FFmpeg filter chains for volume normalization, output limiting, channel selection, resampling. `get_player_dsp_details` provides DSP state for the UI.

- **Output format selection**: `get_output_format` determines the final encoding (FLAC, MP3, AAC, WAV) based on player config. `select_pcm_format` picks the PCM format matching the source. `select_flow_format` picks the format for flow mode streams.

- **Stream types comparison**:
  | Type | AudioBuffer | Mode | Description |
  |------|-------------|------|-------------|
  | Queue tracks | Yes | SEEKABLE | Full buffering with seek |
  | Radio streams | Yes | ROLLING | Short rolling buffer |
  | Announcements | No | — | Short one-off audio, streamed directly |
  | Plugin sources | No | — | Real-time audio, streamed directly |

- **UGP stream integration**: How universal group players connect — they register dynamic routes (`/ugp/{player_id}.{codec}`) and serve the same audio source to multiple members via `UGPStream` (forward reference to `06-grouping.md`).

- **Existing `streams/README.md`**: Verify every claim against the code, incorporate accurate content. The README is thorough and recently updated.

**Key source files:**
- `music_assistant/controllers/streams/controller.py` (~1140 lines)
- `music_assistant/controllers/streams/audio.py` (~2085 lines)
- `music_assistant/controllers/streams/audio_buffer.py` (~645 lines)
- `music_assistant/controllers/streams/constants.py` — buffer sizes, config keys
- `music_assistant/controllers/streams/smart_fades/` — analyzer, fades, mixer
- `music_assistant/controllers/streams/ogg_handler.py` — chained OGG stitching for radio
- `music_assistant/helpers/audio.py` — generic audio utilities
- `music_assistant/helpers/ffmpeg.py` — FFmpeg process management
- `music_assistant/controllers/streams/README.md` — existing thorough documentation

## Writing Principles

Same as prior sub-plans:
- Cite code, not assumptions. Every claim backed by file + method/class name.
- Explain the "why", not just the "what".
- Flag known gaps honestly.
- Keep it skimmable: Mermaid diagrams, tables, short code snippets.
- Human voice, no AI filler.

## Exploration Strategy

1. **Start with `controllers/music.py`** — read the class structure, sub-controller initialization, `search`, `get_item_by_uri`, `sync_library_task`, `on_provider_loaded`, `on_provider_unload`. You don't need to read every media-type-specific method, but understand the orchestration pattern.
2. **Read `controllers/media/base.py`** — the `MediaControllerBase` ABC. Understand `get`, `get_library_item`, `add_item_to_library`, the sync methods. This is the template that all media type controllers follow.
3. **Skim 1-2 specific media controllers** (e.g., `controllers/media/tracks.py`, `controllers/media/artists.py`) to see how they specialize the base.
4. **Read `models/music_provider.py`** — the `MusicProvider` ABC. Focus on the interface methods that providers must implement.
5. **Read `controllers/player_queues.py`** — the full queue controller. Focus on `play_media`, `load`, `play_index`, `_load_item`, `_prepare_next_audio_buffer`, `load_next_queue_item`, `play`, `resume`, `next`, `previous`.
6. **Read `controllers/streams/controller.py`** — the HTTP server and streaming endpoints. Focus on `setup`, `serve_queue_item_stream`, `serve_queue_flow_stream`, `serve_announcement`, `get_stream`, `register_dynamic_route`.
7. **Read `controllers/streams/audio.py`** — the audio processing engine. Focus on `get_stream_details`, `get_media_stream`, `get_queue_item_stream`, `get_queue_flow_stream`, `get_output_format`, `get_player_filter_params`.
8. **Read `controllers/streams/audio_buffer.py`** — the buffer implementation. Focus on `get_buffer`, `fill`, `get_stream`, `get_raw_stream`, seek behavior.
9. **Read `controllers/streams/README.md`** — existing documentation. Verify against code.
10. **Skim `controllers/streams/smart_fades/`** — understand the analyzer, fades, and mixer at a high level.
11. **Read `helpers/ffmpeg.py`** — understand `get_ffmpeg_stream` and how FFmpeg processes are managed.
12. **Git history**: `git log --oneline -20 music_assistant/controllers/player_queues.py` and `git log --oneline -20 music_assistant/controllers/streams/audio.py` for recent refactors.

## Reconciliation with Sub-plan 1-3

### Step 1 — Before exploring (structural vocabulary only)

Skim headings/terms from all 9 prior docs. Key vocabulary to pick up: how the event system works (for queue events), how player commands route (for play/pause/next), how groups interact with streams (for UGP).

### Step 2 — After writing your own docs

Read all 9 prior documents in full. Specific checks:

- Does `00-overview.md` adequately introduce the media/streaming layer in its component map? Does the one-sentence description for MusicController, PlayerQueuesController, and StreamsController match what you found?
- Does `04-player-controller.md` need updates now that we understand how queues and streams interact with players? The queue is the "usual active source" — does the controller doc explain what that means? Does `cmd_play` / `cmd_resume` need more detail about how commands flow from the queue controller?
- Does `06-grouping.md` need updates about UGP streaming, since the flow-mode HTTP stream is central to universal groups? Does the UGP section in grouping correctly describe how `UGPStream` connects to the streaming pipeline?
- Does `15-provider-lifecycle.md` cover how music providers register and how their `get_stream_details` / `get_audio_stream` are called during playback?
- Does `01-event-system.md` cover queue events (`QUEUE_ADDED`, `QUEUE_UPDATED`, `QUEUE_ITEMS_UPDATED`, `QUEUE_TIME_UPDATED`)?

### Step 3 — Bidirectional revision

Fix errors in prior docs. Check if prior docs recontextualize streaming:
- If `06-grouping.md`'s description of UGP reveals that the streaming pipeline doc needs to distinguish between normal streams and UGP streams, revise accordingly.
- If `07-volume.md` describes volume normalization from the player controller perspective, ensure the streaming pipeline doc's description of normalization in the FFmpeg filter chain is consistent.

### Step 4 — Cascade check

If UGP streaming details were added to or corrected in `06-grouping.md`, verify they are consistent with what `10-streaming-pipeline.md` says about the same mechanism.

## What NOT to Cover

These topics belong to Sub-plan 5. Mention only in passing with forward references:

- **Plugin system internals**: How plugins provide audio sources (PluginSource, StreamType.CUSTOM) — Sub-plan 5. Mention that plugin sources bypass the AudioBuffer.
- **Webserver/API internals**: How the main webserver works, JSON-RPC, auth — Sub-plan 5. The streams controller has its own separate HTTP server.
- **Metadata enrichment**: How metadata providers fill in artwork, lyrics — Sub-plan 5.
- **Discovery**: How players/providers are discovered on the network — Sub-plan 5.

## Output Format

Same format as prior sub-plans:
- One-paragraph summary opening each document
- `##` headers for major sections
- At least one Mermaid diagram per document (the streaming pipeline end-to-end is the essential diagram for `10-streaming-pipeline.md`; the library sync flow for `08-media-library.md`; the playback flow for `09-player-queues.md`)
- Tables for comparisons (stream types, buffer modes, normalization modes)
- Short code snippets for essential signatures
- "Key Files" section at the end
- Cross-references to other architecture docs

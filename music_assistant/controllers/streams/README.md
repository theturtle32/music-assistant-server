# Streams Controller Architecture

This document provides an overview of the Music Assistant Streams Controller architecture, including audio buffering, streaming pipeline, and smart fades.

## Table of Contents

- [Overview](#overview)
- [Network Architecture](#network-architecture)
- [Inbound Audio](#inbound-audio)
- [Core Components](#core-components)
- [AudioBuffer](#audiobuffer)
- [StreamsAudio](#streamsaudio)
- [Streaming Pipeline](#streaming-pipeline)
- [Audio Analysis](#audio-analysis)
- [Smart Fades](#smart-fades)
- [Audio Overlay](#audio-overlay)
- [Stream Types](#stream-types)
- [Configuration](#configuration)

## Overview

The Streams Controller is a core controller that manages all audio streaming to players. It provides:
- HTTP streaming endpoints for players on the local network
- Audio buffering with configurable memory usage
- Volume normalization (dynamic, measurement-based, and fixed gain)
- Smart crossfading between tracks
- Flow mode for continuous queue playback
- Audio overlay: a looping sound effect (e.g. rain) mixed into queue playback
- Announcement and plugin source streaming
- Ahead-of-time audio analysis (loudness, beat detection, key detection) by passive readers on the playback buffer

## Network Architecture

The streams controller runs its own dedicated HTTP-only webserver on a separate port (default 8097), independent of the main webserver/API. This design is intentional:

- **No SSL/TLS**: Many audio players (especially embedded devices) have limited resources and struggle with SSL handshakes. Since the stream server only runs on the internal network, encryption is unnecessary.
- **No authentication**: Players need to access streams without credentials. Instead, stream URLs include a **session ID** that is validated on each request to prevent stale or invalid stream attempts.
- **Separate port**: Keeps audio streaming isolated from the API, allowing independent scaling and configuration.

## Inbound Audio

Live announcements (`live_announcements.py`) are the one path where audio travels *into* the stream server rather than out of it: a client pushes raw PCM while a user speaks, and it is played on a player as an ordinary announcement.

This splits across both webservers, because neither can do the job alone:

- The **inbound** half is a WebSocket on the main webserver. Audio from a client is a privileged action, so it needs the authentication and the SSL support that the stream server deliberately does not have. Browsers additionally require a secure context to reach a microphone at all, which only the main webserver can offer.
- The **outbound** half is an ordinary stream server route serving the buffered speech as a WAV. The announcement renderer only ever pulls its audio from a URL, so exposing the clip as one keeps live announcements on exactly the same path as every other announcement.

The announcement is dispatched only once the clip is complete, not while it is still being spoken. Players that announce natively need the whole clip up front: AirPlay renders it to a file and schedules a single synchronized instant across every group member from its exact duration, and Sonos needs the duration to know how long the clip runs. Handing them a clip that is still growing gives one player type a head start and truncates another, so every player gets the same finished clip instead.

A session is identified by an unguessable id that appears only in the stream URL, and it is dropped as soon as the announcement has been played.

## Core Components

```
controllers/streams/
  __init__.py          - Package init, exports StreamsController
  controller.py        - StreamsController: HTTP endpoints, public streaming API
  audio.py             - StreamsAudio: audio processing, stream acquisition, DSP/filters
  audio_analysis.py    - AudioAnalysisController: distributes buffered PCM to audio analysis providers
  audio_buffer.py      - AudioBuffer: in-memory PCM audio buffering with seek support
  audio_processing.py  - AudioProcessingManager: runtime processing chain per queue stream
  constants.py         - Shared constants (buffer sizes, config keys)
  ogg_handler.py       - Chained OGG stream stitching for radio
  strings.json         - Translatable labels for the controller's config entries
  icon.svg             - Controller icon (icon_dark.svg for dark mode)
  smart_fades/         - Smart crossfade planning, rendering and mixing
    planner/           - Candidate/policy transition planner
    bands.py           - Band-power signals over the transition window
    fades.py           - SmartFade ABC plus SmartCrossFade / StandardCrossFade
    filters.py         - FFmpeg filter toolset
    helpers.py         - Shared helpers
    mixer.py           - Crossfade mixing logic
    models.py          - Smart fade data models
    renderer.py        - Renders a planned transition
    structure.py       - Bar-level musical structure detection
    vocal.py           - Vocal-activity contract and collision math
```

Supporting modules in `helpers/`:
- `helpers/audio.py` - Generic audio utilities (PCM helpers, format conversions, silence stripping)
- `helpers/ffmpeg.py` - FFmpeg process management

## AudioBuffer

`AudioBuffer` is the primary interface for all buffered audio streaming. It stores **raw decoded PCM audio** (no filters applied) and serves as the single source of truth for audio data.

### Design Principles

1. **Always-on buffering**: Every queue stream (tracks and radio) goes through an AudioBuffer
2. **Raw PCM only**: The buffer stores decoded audio in original sample rate and bit depth. Filters (volume normalization, playback speed, etc.) are applied when reading via `get_stream()`
3. **Pre-initialization**: Buffers are created and start filling before the player requests the stream, ensuring immediate playback start
4. **Buffer reuse**: Existing valid buffers are reused for seek operations and reconnections
5. **Smart seeking**: Forward seeks within 20 seconds of buffered data wait for the producer; larger seeks trigger a re-fetch at the seek position

### Buffer Modes

- **SEEKABLE** (tracks): Maintains a deque of 1-second PCM chunks with seek support. Old chunks are discarded when the buffer reaches max size
- **ROLLING** (radio/non-seekable): Short FIFO buffer (~15 seconds) where the consumer pops chunks sequentially

### Key Methods

- `AudioBuffer.get_buffer()` - Static factory that creates or reuses a buffer. Reads config, determines mode, starts the analysis reader, starts filling
- `AudioBuffer.get_stream()` - Get processed audio with optional filters/resampling applied
- `AudioBuffer.get_raw_stream()` - Get unprocessed raw PCM audio (playback consumer)
- `AudioBuffer.read_chunk_for_analysis()` - Read one chunk for a passive analysis reader without mutating the buffer; raises when the chunk has been evicted (reader fell behind)
- `AudioBuffer.fill()` - Start filling from an async generator of PCM chunks
- `AudioBuffer.ready` - Event set when enough chunks are buffered past the seek point (threshold-based)

### Buffer Lifecycle

```
1. _load_item() fetches stream details, creates buffer with wait_ready=True
2. Buffer starts filling from get_media_stream() in background
3. Analysis (loudness, smart fades) reads the same buffer in parallel, at lower priority
4. Player requests stream -> get_queue_item_stream() calls buffer.get_stream()
5. 60s before the end of the source stream: prepare_next_audio_buffer() pre-fills next track
6. _cleanup_stale_queue_buffers() clears old buffers to free memory
```

### Error Handling

- Producer errors are captured and surfaced when consumers try to read
- Consumers can drain remaining buffered data before the error surfaces at EOF
- Errors bubble up as `AudioError` through the streaming chain

## StreamsAudio

`StreamsAudio` is the audio processing sub-controller, initialized as `self.audio` on the StreamsController. It handles all audio-related logic that needs access to the MusicAssistant instance:

- **Stream acquisition**: `get_stream_details`, `get_media_stream`, and `_resolve_media_stream_source` (the per-stream-type resolution that replaced the separate radio/HTTP/file helpers)
- **Queue streaming**: `get_queue_item_stream`, `get_queue_item_stream_with_smartfade`, `get_queue_flow_stream`
- **Format selection**: `get_output_format`, `select_pcm_format`, `select_flow_pcm_format`
- **DSP and output plans**: `get_player_output_plan` (returns the executable filters plus the client-facing `AudioOutputDetails`)
- **Crossfade management**: `crossfade_allowed`, `clear_crossfade_handover`

`AudioProcessingManager`, initialized as `self.audio_processing` on the
StreamsController, combines queue processing and per-player output plans into complete
`AudioProcessingChain` snapshots attached to `StreamDetails`.

`AudioAnalysisController`, initialized as `self.audio_analysis` on the StreamsController,
owns the analysis side: it starts analysis sessions on the registered audio analysis
providers, feeds them PCM read from the playback buffer, and persists their results.

## Streaming Pipeline

```
Music Provider -> get_media_stream() -> FFmpeg (decode to raw PCM)
    -> AudioBuffer (raw PCM storage; audio analysis reads from here in parallel)
    -> buffer.get_stream() -> Optional: FFmpeg (volume normalization, speed, fade-in)
    -> Optional: Smart Fades (crossfade mixing between tracks)
    -> FFmpeg (encode to output format with player-specific DSP)
    -> HTTP Response / Direct PCM stream
```

### Stream Entry Points

1. **HTTP endpoints** (`serve_queue_item_stream`, `serve_queue_flow_stream`): Used by players that consume HTTP streams (Chromecast, DLNA, Sonos, etc.)
2. **Direct PCM** (`get_stream`): Used by player providers that consume raw PCM directly (AirPlay, Sendspin, etc.)

## Audio Analysis

Analysis is a **passive observer** of the playback buffer: nothing is pushed to it and the audio path is not modified. The analysis reader keeps its own cursor over the buffer's retained chunks, so a slow analyzer falls behind and loses its session rather than holding up the playback stream.

```
AudioBuffer.get_buffer()
    -> mass.streams.audio_analysis.start_analysis(buffer, streamdetails)   [fire-and-forget task]
        -> provider.start_analysis() on every available audio analysis provider
        -> AudioAnalysisController._buffer_reader_worker()
            -> buffer.read_chunk_for_analysis(cursor)     [1-second chunks, non-mutating]
            -> provider.process_pcm_chunk() fanned out to all accepted providers
            -> provider.finalize() at clean EOF, provider.cancel() otherwise
```

- A session is only started for a **freshly created** buffer at seek position 0, and never for `AUDIO_SOURCE` or `SOUND_EFFECT` media
- Providers **decline** a session when the track already has analysis at the provider's current `analysis_version`, or when the track exceeds the provider's `max_analysis_duration`; a session with no accepting provider is never started
- The buffer's only hook is `register_cancel_callback()`, used to drop the session when the buffer is torn down (track skipped, buffer cleaned up)
- If the reader falls a full window behind and the chunk it needs has already been evicted, the session is dropped rather than allowed to slow the producer
- A stream that ends short of 90% of the expected duration is discarded instead of finalized, so a died-mid-track source can't persist truncated analysis
- At most 2 realtime sessions run per queue (the playing track and its preloaded successor); a provider that exceeds the per-chunk hang guard is evicted from the session

The same provider interface is reused by the nightly **background scan**, which streams local files through FFmpeg for tracks that have no (current) analysis yet.

### Analysis Providers

| Provider | Produces | Notes |
|----------|----------|-------|
| `loudness_analysis` | EBU R128 integrated loudness | Feeds PCM into an FFmpeg `ebur128` process, capped at 600 seconds of audio. Result is stored so future playback can use measurement-based normalization instead of dynamic mode |
| `smart_fades` | Beats, downbeats, musical key, RMS energy, spectral centroid, vocal activity | Beat This! neural beat tracker plus S-KEY and FireRed AED; see the [Smart Fades provider README](../../providers/smart_fades/README.md) |
| `sonic_analysis` | librosa scalars and CLAP embeddings | Describes how a track sounds, powering similarity and mood-based features |
| `acoustid_lookup` | MusicBrainz recording ID and ISRC | Computes a Chromaprint fingerprint and resolves it via AcoustID; produces no signal analysis of its own |

Results are persisted by `AudioAnalysisController` and read back via `get_audio_analysis()`, so a track is analyzed once and reused on later playback.

## Smart Fades

The smart fades system provides intelligent crossfading between tracks:

- **Smart Crossfade**: Analyzes audio beats to detect natural fade points
- **Standard Crossfade**: Fixed-duration overlap crossfade with silence stripping
- Operates in both flow mode (continuous stream) and per-item mode (gapless playback)

## Audio Overlay

The audio overlay is a per-queue feature (configured via `player_queues/overlay`) that mixes a
looping sound effect — any `sound_effect` media item offered by a provider — into the queue's
audio stream:

- Mixing happens once per queue stream (ffmpeg `amix`, overlay looped via `-stream_loop -1`),
  so all (synced) players consuming the stream hear the identical mix.
- An active overlay forces flow mode: the overlay must play continuously across track
  boundaries, which is impossible with per-item stream requests. Radio is the exception —
  it always plays as a single long-lived stream and is wrapped per-request instead.
- The internal PCM format is upgraded to F32 (like crossfade/DSP) for clipping-free headroom.
- Failures degrade gracefully: when the overlay source can not be resolved, playback simply
  continues without overlay; when the overlay input dies mid-stream, ffmpeg keeps passing
  the main audio. Music playback is never interrupted by the overlay.
- Note: audio already sitting in a player's (pre)buffer is unaffected by overlay changes,
  which is why the queue controller restarts playback on an audible change. For the same
  reason a seek can momentarily shift the overlay position — acceptable for ambient content.

## Stream Types

| Type | AudioBuffer | Description |
|------|-------------|-------------|
| Queue tracks | Yes (SEEKABLE) | Regular track playback with full buffering |
| Radio streams | Yes (ROLLING) | Short rolling buffer, non-seekable |
| Announcements | Yes (SEEKABLE) | Short one-off audio (TTS), rendered once and shared by all consumers |
| `AUDIO_SOURCE` items | No | Real-time audio from a plugin provider (Spotify Connect, an AirPlay/AriaCast/VBAN receiver), streamed directly. Queue-item sources are served from `/single/`; a source attached to a player is served from `/source/`. The old `PluginSource` model and its dedicated endpoint are gone |
| Sound effects | No | Overlay sources, mixed in as an extra FFmpeg input |

## Configuration

Key configuration entries (in streams controller config):

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `buffer_size` | String | Memory-dependent (`maximum` >=8GB, `balanced` >=4GB, `minimal` <4GB) | Audio buffer size preset |
| `volume_normalization_radio` | String | `fallback_dynamic` | Normalization mode for radio |
| `volume_normalization_tracks` | String | `fallback_dynamic` | Normalization mode for tracks |
| `volume_normalization_fixed_gain_radio` | Float | `-6` | Fixed/fallback gain (dB) for radio |
| `volume_normalization_fixed_gain_tracks` | Float | `-6` | Fixed/fallback gain (dB) for tracks |
| `volume_normalization_target` | Integer | `-14` | Target loudness in LUFS (advanced) |
| `allow_crossfade_same_album` | Boolean | `false` | Whether to crossfade consecutive album tracks |
| `publish_ip` | String | `auto` | IP address communicated to players in stream URLs (advanced) |
| `bind_port` | Integer | `8097` | Port the streams webserver binds to (advanced) |
| `bind_ip` | String | `0.0.0.0` | Interface the streams webserver binds to (advanced) |
| `smart_fades_log_level` | String | `GLOBAL` | Log level for the Smart Fades mixer and analyzer (advanced) |
| `background_scan_concurrency` | Integer | `2` (`1` below 4 cores) | Tracks analyzed concurrently during the nightly background scan |

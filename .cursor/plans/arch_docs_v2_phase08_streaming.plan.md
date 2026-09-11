---
name: arch_docs_v2_phase08_streaming
overview: "Phase 8. Refresh 10-streaming-pipeline.md: audio analysis is now a passive observer, AudioProcessingManager publishes the processing chain and bit-perfect fidelity onto StreamDetails, audio overlay forces flow mode, the DSP filter catalog grew while the output limiter was removed, the dedicated plugin-source endpoint is gone, and crossfade/normalization are queue-scoped."
todos:
  - id: preflight
    content: "Pre-flight: verify the streams module map, endpoints, buffer thresholds, DSP plan, and overlay behavior against the working tree"
    status: completed
  - id: modules
    content: "10-streaming-pipeline.md: refresh the module map and controller initialization for audio_processing.py"
    status: completed
  - id: endpoints
    content: "10-streaming-pipeline.md: remove the /pluginsource endpoint and document the AUDIO_SOURCE path through /single/ and /flow/"
    status: completed
  - id: streamdetails
    content: "10-streaming-pipeline.md: fix get_stream_details (just-in-time loudness hydration, streams-global target, queue-scoped enablement)"
    status: completed
  - id: analysis_handoff
    content: "10-streaming-pipeline.md: rewrite the audio analysis hand-off as a passive buffer reader; fix buffer ready thresholds"
    status: completed
  - id: overlay
    content: "10-streaming-pipeline.md: add an audio overlay section and note the flow-mode forcing conditions"
    status: completed
  - id: dsp
    content: "10-streaming-pipeline.md: rewrite the DSP chain section (get_player_output_plan, AudioProcessingChain, new filters, limiter removal, linked players)"
    status: completed
  - id: fidelity
    content: "10-streaming-pipeline.md: add an audio processing metadata / bit-perfect fidelity section"
    status: completed
  - id: crossfade
    content: "10-streaming-pipeline.md: correct crossfade configuration and mixer build/mix split; slim smart fades down to a cross-link to the new 17-smart-fades.md"
    status: completed
  - id: keyfiles
    content: "10-streaming-pipeline.md: refresh the Key Files table and add a pointer to the in-tree streams README"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 8 — Streaming pipeline

File: `docs/architecture/10-streaming-pipeline.md` (40–60% rewrite).

Ordering note: this phase slims the smart-fades material down to a cross-link and Phase 9 creates
`17-smart-fades.md`. Either write the cross-link now and create the target in Phase 9, or run the
phases back to back — do not leave a dangling link on a pushed commit for long.

Related in-tree README: `music_assistant/controllers/streams/README.md`. It is current on overlay
and `AudioProcessingManager`, but its **Analyze Callbacks section is stale** — do not rely on it
there. (Phase 1 fixes the README itself; keep the two consistent.)

## Module map

`controllers/streams/` now contains a new `audio_processing.py`, extracted from `audio.py` in #4793:

- `AudioProcessingManager` plus session/item/output tracking.
- Publishing `AudioProcessingChain`, `AudioOutputDetails`, and `AudioQueueProcessing` onto
  `StreamDetails`.
- `get_audio_quality()`, `get_media_session_id()`, `get_normalization_details()`.
- `_is_bit_perfect()` / `AudioFidelity` (extended by #5087, #5042).

`audio.py` keeps stream acquisition, crossfade, overlay, and FFmpeg output encoding, and calls
`mass.streams.audio_processing.update_*()` at runtime. `StreamsController.__init__` now also builds
`self.audio_processing = AudioProcessingManager(mass)` — the doc lists only `self.audio` and
`self._audio_analysis`.

## Endpoints

The `/pluginsource/{plugin_source}/{player_id}.{fmt}` endpoint is **removed**.
`MediaType.AUDIO_SOURCE` items stream through `/single/` or `/flow/`, with a WAV passthrough fast
path for live sources (`resolve_stream_url` forces WAV for `AUDIO_SOURCE`). Plugin lifecycle hooks
(`on_source_selected` / `on_source_unselected`) fire from `serve_queue_item_stream`. Phase 12 owns
the plugin-side model; here document the streaming-side path.

Also correct the Stream Types section: `MediaType.AUDIO_SOURCE` bypasses `AudioBuffer` **and**
normalization via `get_audio_source_stream()`, but other plugin-backed items can still use the
normal queue paths. And note that `CUSTOM` streams get server-side silence keepalive while
`NAMED_PIPE` producers must keep writing silence themselves.

## Stream details and loudness

The doc says loudness is loaded in `get_stream_details` via `mass.music.get_loudness`. Loudness is
now hydrated just-in-time in `get_queue_item_stream()` from
`audio_analysis.get_audio_analysis(..., priority=(loudness_analysis,))`. The target LUFS comes from
the streams-global `CONF_VOLUME_NORMALIZATION_TARGET` (#4369) while normalization *enablement* is
queue-scoped (#4373).

## Audio analysis hand-off

Rewrite. Analysis is a **passive observer** (#4442): `AudioBuffer.read_chunk_for_analysis()` feeds
`AudioAnalysisController._buffer_reader_worker()`, and playback never waits on analysis. The
signature is `start_analysis(audio_buffer, streamdetails)` — not
`start_analysis(session_id, streamdetails, audio_format)` with a `_distribute_chunk(session_key, pcm)`
push. `CHUNK_HANG_GUARD_SECONDS` is 120.0, and a session is evicted if analysis falls behind the
buffer window. Keep the detail here light and cross-link `16-audio-analysis.md` (Phase 9).

Also fix the `AudioBuffer` ready thresholds: **8s** for crossfade, **5s** for dynamic tracks (3s for
radio), **2s** default. The doc says 10s / 5s / 2s.

## Audio overlay

New section (#4674). Overlay forces flow mode (as do non-gapless players), and mixing runs through
`get_overlay_mixed_stream()` / `get_ffmpeg_overlay_stream()`. The in-tree streams README has good
source material for this — summarize and link, don't copy.

## DSP chain

- `get_player_filter_params` → **`get_player_output_plan()`**, publishing an
  `AudioProcessingChain` on `StreamDetails`.
- The fixed output `alimiter` was **removed** (#4901). The doc still describes it.
- New filters to add: gain and balance (#4857), high/low-pass (#4944), transpose via rubberband
  (#5005), and `ComplexFilter` for multi-input DSP such as convolution (#4872).
- Synchronized and linked players are now included in shared output paths (#4856).
- Remove references to the deleted `get_player_dsp_details` / `get_stream_dsp_details`.

## Audio processing metadata and bit-perfect

New section. `AudioFidelity.bit_perfect` is computed in `audio_processing._is_bit_perfect()`:
lossless or hi-res only, with no normalization, crossfade, overlay, DSP, or channel mapping
(#4793, #5087).

## Crossfade and smart fades

- Crossfade on/off and mode are **queue-scoped** (#4373). The effective mode comes from
  `StreamsController.get_crossfade_mode()`, which combines the queue settings with
  `smart_fades_available` (requires a non-MINIMAL buffer and the smart_fades analysis provider
  loaded).
- `SmartFadesMixer` split into **`build()`** (loads analysis, constructs `SmartCrossFade` or
  `StandardCrossFade`) and **`mix()`** (executes only). The smart path requires BPM and beats on
  both tracks, otherwise it falls back to standard (vocal-aware since #4816).
- The fades table names `FrequencySweepFilter` and `TrimFilter`. Current filters are `ShelfFilter`,
  `PeakFilter`, `FadeInTrimFilter`, and `FadeOutTrimFilter`, with DJ-style bass swap / 3-band EQ
  driven by `band_rms` envelopes (#4591, #4536).
- Then **slim the section** to this summary plus a link to `17-smart-fades.md`.

## Key files and network

- Add `audio_processing.py` and `audio_analysis.py`; expand the `smart_fades/` entry to
  `planner/`, `renderer.py`, `models.py`, `bands.py`, `structure.py`, `vocal.py`.
- Add a pointer to `music_assistant/controllers/streams/README.md`.
- Network Architecture: check the streamserver publish-address behavior (multi-address publishing
  landed in #4646) and align with Phase 15's discovery edits.
- Note `music_assistant/helpers/shared_playback.py` only insofar as it affects stream ownership;
  Phase 13 owns shared playback sessions.

## Verification

- `rg "AudioProcessingManager|AudioProcessingChain|AudioFidelity|get_player_output_plan|get_overlay_mixed_stream|read_chunk_for_analysis|CHUNK_HANG_GUARD_SECONDS"`.
- Confirm removals: `rg "pluginsource|alimiter|get_player_filter_params|get_stream_dsp_details"`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): streaming pipeline refresh for audio processing, overlay and DSP

Phase 8 of the upstream/dev refresh.
```

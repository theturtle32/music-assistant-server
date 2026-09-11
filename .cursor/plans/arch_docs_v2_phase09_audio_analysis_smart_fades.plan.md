---
name: arch_docs_v2_phase09_audio_analysis_smart_fades
overview: Phase 9. Rewrite the session model, throttling, and data model in 16-audio-analysis.md, add the two new analysis providers (sonic_analysis, acoustid_lookup) and the failure-tracking subsystem, and create a new 17-smart-fades.md covering the planner/selection/assembly/renderer stack that replaced the old monolithic mixer.
todos:
  - id: preflight
    content: "Pre-flight: verify the analysis session model, throttle constants, provider hook surface, AudioAnalysisData fields, and the smart fades planner stack against the working tree"
    status: completed
  - id: aa_session
    content: "16-audio-analysis.md: rewrite the session model and architecture diagram as a passive buffer observer"
    status: completed
  - id: aa_throttle
    content: "16-audio-analysis.md: rewrite CPU throttling and background scan (semaphore, niced pool, solo lock, model unload, concurrency clamp, pacing floor)"
    status: completed
  - id: aa_hooks
    content: "16-audio-analysis.md: extend the AudioAnalysisProvider hook surface (model loading, offloading, AudioAnalysisError, failure recording)"
    status: completed
  - id: aa_data
    content: "16-audio-analysis.md: correct AudioAnalysisData field types and add rhythmic_regularity and extra_data"
    status: completed
  - id: aa_providers
    content: "16-audio-analysis.md: add sonic_analysis and acoustid_lookup; update the smart_fades provider entry for analysis_version 3"
    status: completed
  - id: aa_api
    content: "16-audio-analysis.md: add the failure/coverage/waveform API commands, persistence cleanup, and downstream consumers"
    status: completed
  - id: sf_newdoc
    content: Create docs/architecture/17-smart-fades.md covering the planner to renderer execution stack
    status: completed
  - id: crosslinks
    content: Add cross-links from 16-audio-analysis.md and 10-streaming-pipeline.md to 17-smart-fades.md
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 9 — Audio analysis and smart fades

Files: `docs/architecture/16-audio-analysis.md` (50%+ rewrite) and a new
`docs/architecture/17-smart-fades.md` (~150–250 lines).

`16-audio-analysis.md` was written in round 1, so the drift here is recent upstream work rather
than original inaccuracy. Smart fades gets its own file because execution alone spans ~15 modules
with planner policies, vocal protection, band EQ, and renderer filter chains — far more than the
analysis-provider hook surface it was sharing space with.

## `16-audio-analysis.md`

### Session model (rewrite)

The architecture diagram shows `start_analysis(session_id, ...)`, a per-session `asyncio.Queue`,
and a `_chunk_worker`. Replace with the passive buffer reader model (#4442): analysis reads from the
buffer and can never block decode. Also:

- `CHUNK_PROCESS_TIMEOUT_SECONDS = 1.0` → `CHUNK_HANG_GUARD_SECONDS = 120.0`, with stuck providers
  evicted from the session.
- `REALTIME_ANALYSIS_MAX_SESSIONS = 2` per queue (#4451).
- Incomplete streams are discarded below `ANALYSIS_MIN_COMPLETENESS_RATIO = 0.9` (#4738).

### CPU throttling and background scan

The doc mentions only `torch.set_num_threads(_aa_thread_budget())`. Add the `InstrumentedSemaphore`
concurrency cap, the niced `ThreadPoolExecutor` (`ANALYSIS_THREAD_NICE = 10`), the
`analysis_solo_lock` held during active playback (#4449), `inference_thread_budget()` shared with
BLAS (#4568, #4311), and idle model unload after 300s (#4452).

Background scan concurrency is clamped to **[1, 16]** (doc says [1, 8]), with a per-track timeout of
`max(300, duration × 1.5)` and a 0.25s pacing floor between chunk dispatches (#4568).

### Provider hook surface

Missing from the doc: `max_analysis_duration`, `has_unloadable_models`, `ensure_models_loaded()`,
`unload_idle_models()`, `_run_offloaded()` / `_run_offloaded_timed()`, and the
`AudioAnalysisError` → `record_analysis_failure()` → `DB_TABLE_AUDIO_ANALYSIS_FAILURES` path
(#4167). Also note that the base class catches `AudioAnalysisError`, records the failure, and wraps
`post_analysis` errors without breaking cleanup.

### Data model

`beats`, `downbeats`, `rms_energy`, and `spectral_centroid` are plain `list[float]`, not
`NDArray[float32]` — numpy appears only at compute sites, deliberately, so numpy is not required on
all installs. Add `rhythmic_regularity` and `extra_data` (provider-specific: `clap_embedding`,
`vocal_activity`, `band_rms`, AcoustID identifiers).

### Providers

| Provider | Type | Notes |
| --- | --- | --- |
| `loudness_analysis` | `AudioAnalysisProvider` (builtin) | already documented |
| `smart_fades` | `AudioAnalysisProvider` (optional) | now `analysis_version = 3` |
| `sonic_analysis` | `AudioAnalysisProvider` (optional, ML-heavy) | **new** |
| `acoustid_lookup` | `AudioAnalysisProvider` (optional, beta) | **new** |
| `sonic_similarity` | **`PluginProvider`**, not an analysis provider | consumes sonic_analysis + smart_fades output |

- **`sonic_analysis`** (#4307): CLAP embeddings plus librosa scalars, with a vendored CLAP model
  under `providers/sonic_analysis/vendored_clap/`. Note the RAM/CPU gates and that the vendored
  model is third-party.
- **`acoustid_lookup`**: Chromaprint fingerprinting → MusicBrainz recording ID.
- **`smart_fades` provider** now also produces FireRed vocal activity
  (`extra_data["vocal_activity"]`, #4786), 4-band RMS envelopes (`extra_data["band_rms"]`), and
  beats-per-bar / time-signature DBN output (#4580). Dependencies include
  `kaldi-native-fbank` — check the manifest for the current pin.

### API and persistence

Add the `audio_analysis/wave_form`, `audio_analysis/coverage`, and `audio_analysis/failures`
commands (#4626, #4167). Persistence cleanup now also recovers from corrupt rows (#4721), and
failures are tracked in their own table.

### Downstream consumers

Add a short section: `sonic_similarity` (similar tracks and a discover row), and
`providers/hue_entertainment/analyzer.py`, which now derives Sendspin beat schedules from persisted
smart_fades analysis rather than running librosa inline. Link to the Hue provider README rather than
detailing it.

## New file: `docs/architecture/17-smart-fades.md`

Cover the current pipeline:

```
SmartFadesMixer.build()  →  SmartCrossFade.build()
                              → SmartCrossFadePlanner.plan()      planner/planner.py
                                   context.py     TransitionContext from AudioAnalysisData
                                   candidates.py  anchor / candidate generators
                                   policies.py    rejection and penalty scoring
                                   selection.py   CandidateSelector
                                   assembly.py    PlanAssembler, EmergencyHandoffFactory
                              → TransitionRenderer.render()       renderer.py
                                   Crossfade, Shelf, Peak, GradualTimeStretch, FadeIn/OutTrim
                              → SmartFade.apply() via FFmpeg
SmartFadesMixer.mix(smart_fade, ...)  executes the pre-built fade only
```

Supporting modules: `models.py` (`TransitionPlan`, `Deck`, `BandProfile`, …), `bands.py`,
`structure.py`, `vocal.py` (FireRed vocal windows), `helpers.py`, `filters.py`, `fades.py`,
`mixer.py`.

Also cover:

- **What replaced what.** The old model was a monolithic `SmartFadesMixer.mix()` with inline
  beat-matching, `FrequencySweepFilter` / `TrimFilter`, and a ~0.3 confidence gate.
  `music_assistant/models/smart_fades.py` was **deleted**.
- **The analysis/execution split.** Analysis (beats, band RMS, vocal activity) lives in
  `providers/smart_fades/` at `analysis_version = 3`; execution reads persisted rows via
  `audio_analysis.get_audio_analysis(..., priority=(smart_fades,))`.
- **Vocal and energy awareness** (#4816) and the silence-stranding fix on energy-drop transitions
  (#4926).
- **DJ-style band EQ** (#4591, #4536).
- Link to `providers/smart_fades/README.md` for provider-level operational detail.

Driving PRs: #4532, #4580, #4591, #4536, #4786, #4816, #4926.

## Cross-links

`16-audio-analysis.md` → `17-smart-fades.md` for execution; `10-streaming-pipeline.md` (Phase 8) →
`17-smart-fades.md`. The `README.md` catalog entry is added in Phase 16.

## Verification

- `rg "ANALYSIS_MIN_COMPLETENESS_RATIO|REALTIME_ANALYSIS_MAX_SESSIONS|ANALYSIS_THREAD_NICE|analysis_solo_lock|inference_thread_budget|record_analysis_failure"`.
- `rg "SmartCrossFadePlanner|TransitionRenderer|EmergencyHandoffFactory|CandidateSelector"`.
- Confirm `music_assistant/models/smart_fades.py` is gone.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): audio analysis refresh and new smart fades doc

Phase 9 of the upstream/dev refresh.
```

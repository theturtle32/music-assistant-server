# 17 — Smart Fades Execution

Smart fades is Music Assistant's beat-matched, musically-aware crossfade engine. It lives in `music_assistant/controllers/streams/smart_fades/` and answers one question: given two tracks' stored analysis and however many seconds of the outgoing track's tail are held in memory, *how* should they be joined?

The subsystem splits in two, and keeping the halves straight is the key to reading either:

| Half | Where | Produces |
|---|---|---|
| **Analysis** | `providers/smart_fades/` (an audio-analysis provider, `analysis_version = 3`) | Beats, downbeats, beats-per-bar, key/mode, RMS energy, band envelopes, vocal activity — persisted per track |
| **Execution** | `controllers/streams/smart_fades/` (this document) | A `TransitionPlan`, then a rendered filter chain, then mixed PCM |

Execution never analyzes audio. It reads persisted rows through `mass.streams.audio_analysis.get_audio_analysis(item_id, provider, priority=(SMART_FADES_ANALYSIS_DOMAIN,))` — the `priority` tuple insisting on the smart-fades provider's own row rather than a merged view that another provider might have contributed conflicting fields to. See [16-audio-analysis.md](16-audio-analysis.md) for the analysis half and [10-streaming-pipeline.md](10-streaming-pipeline.md#crossfade) for where the mixer plugs into the audio path.

## What this replaced

The engine was refactored from a monolith into a plan/render architecture in #4532, and the shape of the old design explains most of the new one's structure.

| Was | Is |
|---|---|
| `SmartFadesMixer.mix()` did everything: loaded analysis, beat-matched inline, built filters, executed | `build()` plans and primes; `mix()` only executes an already-built fade |
| Beat matching mutated a scratchpad on the planner (`self._pristine_*` snapshots, re-anchoring in place) | An immutable `TransitionContext` every candidate build reads and none mutates |
| One transition computed directly, take it or leave it | Many *candidates* generated, scored by independent policies, best one wins |
| A ~0.3 analysis-confidence gate decided smart vs standard | Requires BPM and beats on both tracks; feasibility is decided by candidate generation and policy rejection |
| `FrequencySweepFilter`, `TrimFilter` | `ShelfFilter`, `PeakFilter`, `FadeInTrimFilter`, `FadeOutTrimFilter` |
| `music_assistant/models/smart_fades.py` held shared models | **Deleted.** Models live in `controllers/streams/smart_fades/models.py`, next to the only code that uses them |

The payoff of the split: a `TransitionPlan` is pure data over the two analysis rows and the available holdback window, so it can be computed and reasoned about before a single audio byte is buffered, and alternative strategies drop in as sibling `TransitionPlanner` subclasses.

## Pipeline

```
StreamsAudio.get_queue_item_stream_with_smartfade / get_queue_flow_stream
  │
  ├─ SmartFadesMixer.build(...)                                     mixer.py
  │    ├─ _load_analyses()   → get_audio_analysis(priority=(smart_fades,))
  │    ├─ _build_smart_crossfade()  → SmartCrossFade(...)            fades.py
  │    │     └─ SmartCrossFade.build()
  │    │          ├─ SmartCrossFadePlanner.plan()                    planner/planner.py
  │    │          │    ├─ build_transition_context()                 planner/context.py
  │    │          │    ├─ default_generators() → CandidateSpec[]     planner/candidates.py
  │    │          │    ├─ CandidateFactory.build() → Candidate[]     planner/candidates.py
  │    │          │    ├─ CandidateSelector.select(default_policies()) planner/selection.py
  │    │          │    │                                             planner/policies.py
  │    │          │    ├─ RescueAnchorGenerator  (if all rejected)   planner/candidates.py
  │    │          │    └─ PlanAssembler.finalize() → TransitionPlan  planner/assembly.py
  │    │          │       or EmergencyHandoffFactory.build()         planner/assembly.py
  │    │          └─ TransitionRenderer.render(plan) → Filter[]      renderer.py
  │    │                                                            + CrossfadeTimingInfo
  │    └─ _build_standard_crossfade()  → StandardCrossFade           fades.py  (fallback)
  │
  └─ SmartFadesMixer.mix(smart_fade, ...) → SmartFade.apply()        fades.py
                                             └─ FFmpeg
```

Reading it as a sentence: **plan in seconds, render into filters, apply to bytes.** The planner touches no audio at all; the renderer is the first place bytes re-enter, reconciling the plan's second-based sizing against the actual buffer lengths; `apply()` runs the resulting chain through FFmpeg.

## Degradation chain

Nothing here is allowed to break playback, so every stage has a fallback and the last one cannot fail.

```
SMART_CROSSFADE requested
  └─ both tracks have bpm + beats?           no → StandardCrossFade
       └─ any feasible candidate built?      no → SmartFadeNotApplicable → StandardCrossFade
            └─ any candidate survives policy rejection?
                 no → RescueAnchorGenerator: a modest, late-anchored rung
                      └─ still nothing? → EmergencyHandoffFactory: click-free equal-power handoff
                 yes → PlanAssembler.finalize(winner)
```

`SmartFadeNotApplicable` is the planner's way of saying "these two tracks cannot yield this transition, fall back" — distinct from an error. `_build_smart_crossfade` catches it at debug level and any other build failure at warning level, returning `None` so the mixer builds a standard crossfade instead.

One detail that matters for quality: when the smart build falls back, it **retains the outgoing track's analysis row** and hands it to `_build_standard_crossfade`. The standard fade uses it for vocal-aware silence retention — computing how much of the tail must be kept so an audible vocal is not clipped, instead of blindly stripping trailing silence (#4816).

## The planner

`SmartCrossFadePlanner.plan(fade_out_analysis, fade_in_analysis, buffer_duration)` is deliberately thin — it orchestrates five collaborators and owns no logic of its own.

### `context.py` — the immutable facts

`build_transition_context()` produces a frozen `TransitionContext` holding every **per-transition** fact: the two `Deck`s (each a track's analysis plus the beat and downbeat grids usable for *this* transition), their `BandProfile`s, the outgoing tail's energy and kick anchors and audible boundary, the chosen `TransitionTier`, the vocal-activity masks, and the coda / fade-onset detections.

What it deliberately excludes is anything that depends on a candidate's chosen overlap length or re-anchor point — those anchor-*dependent* derivations are the candidate factory's job. Building this once, frozen, is what replaced the old planner's mutable scratchpad: two builds of the same candidate spec are guaranteed identical.

### `candidates.py` — intent, then timing

Two value types, and the distinction between them carries weight:

- A **`CandidateSpec`** is a generator's declared *intent* — which tier rung, which anchor and entry point, which relaxation was applied — before any plan exists.
- A **`Candidate`** is that spec paired with its timed `TransitionPlan` and computed `PlanMetrics`, ready to be scored.

`CandidateFactory.build(spec)` produces **timed** candidates only: anchor, overlap timing, tempo ramp, trims, metrics. EQ is deliberately absent, because scoring never needs it — so the expensive EQ assembly runs once, for the winner, rather than for every candidate. Each `build()` derives its anchored tail fresh from the context.

`default_generators()` supplies the anchor and candidate generators; `RescueAnchorGenerator` is held back for the all-rejected path.

### `policies.py` and `selection.py` — scoring

Each `Policy` independently judges one built candidate against the shared context and returns a `Verdict`: either an outright **rejection** (disqualified) or a soft **penalty** folded into ranking. One rule per class, so selection can compose, reorder or disable them without touching the scoring math.

`CandidateSelector.select()` runs **every** policy on **every** candidate — no short-circuit on the first rejection — and picks the lowest-penalty survivor. Running them all is what makes the debug log show a complete scoreboard rather than whichever rule happened to fire first, which is the difference between being able to tune this and not.

### `assembly.py` — EQ for the winner, and the last resort

`PlanAssembler.finalize(candidate)` computes the bass/mid/high handover EQ exactly once, for the winner. `EmergencyHandoffFactory.build()` produces the click-free equal-power fallback used when every phrased candidate still collides with the incoming vocal.

### Supporting signal modules

| Module | Role |
|---|---|
| `bands.py` | Turns the analyzer's `band_rms` envelopes into bar-level power statistics on the track's own downbeat grid. Planner gates read **power fractions**, which cancel the per-track peak normalization — making them the only cross-track-comparable quantity the stored data supports |
| `structure.py` | Bar-level structure detection over a `BandProfile`: mastered fadeouts, valid outro/coda zones. Every energy feature is self-referenced against the track's own full-track active-bar medians, so nothing here compares material across tracks. It runs no vocal classifier of its own — the coda detector consumes the FireRed `VocalMask` to keep sung material out of a candidate exit zone |
| `vocal.py` | Parses the optional 1800-bin `vocal_activity` list out of `extra_data`, turns it into hysteresis-gated vocal windows, and scores how much two tracks' vocals would collide inside a candidate crossfade. Works over plain floats and lists — **no numpy** — so a missing or malformed timeline never drags numpy onto a path that would otherwise stay free of it |
| `helpers.py` | `SMART_CROSSFADE_DURATION` (45 s), tempo-step computation, downbeat extrapolation, dB ramps |

## The plan

`TransitionPlan` (`models.py`) is the renderer-agnostic description of a transition — every decision, no audio bytes and no FFmpeg filters. All times are in the outgoing track's buffer-local seconds.

| Field | Meaning |
|---|---|
| `tier` | How ambitious the transition is; drives overlap length, tempo and EQ |
| `fade_out_window` | Audible end of the fade-out tail |
| `crossfade_duration` | Overlap length |
| `eq_plan` | Bass-swap EQ: who owns the low end, and when it swaps |
| `tempo_plan` | Tempo ramp schedule for the outgoing track |
| `fadeout_trim` | Where the outgoing content ends and how much was dropped |
| `fadein_trim_start` | Seconds trimmed off the incoming head for beat alignment |
| `metrics` | `PlanMetrics` telemetry |

### Tiers

`TransitionTier` is decided from tempo compatibility, key and blendability:

| Tier | When | Result |
|---|---|---|
| `FULL_BLEND` | Within stretch range *and* keys compatible | Long, fully-featured DJ blend |
| `TEMPO_BLEND` | Within stretch range but keys clash | Shorter, energy-anchored blend |
| `QUICK_FADE` | Tempos incompatible or material not blendable | Short downbeat-snapped fade |

### `EqPlan` — DJ-style band EQ

The bass-swap EQ (#4536), extended to a content-aware 3-band handover driven by the band envelopes (#4591). `EqPlan` holds a `swap_at` position plus up to six `ShelfSchedule`s — low, high and mid, for each of the outgoing and incoming sides. A `None` schedule means that shelf is bypassed because it came out shallower than the bypass floor; `EqPlan.neutral()` renders no shelves at all.

Two coordinate systems coexist here and mixing them up would desynchronize the EQ from the audio: **A-side (outgoing) schedules are in input time**, pre-stretch, while **B-side (incoming) schedules are in post-trim time**. `ShelfSchedule.gain_at()` interpolates a scheduled gain, clamping at the ends.

`EqPlan` exposes two adjustment methods the assembler uses to reconcile EQ with a vocal-protected or tightened transition: `with_mid_depth_scaled()` (shrink the mid/vocal handover, bypassing it entirely below a depth floor) and `with_low_ramps_steepened()` (tighten the low ramp span around the swap while leaving the endpoint gains alone).

### `TempoPlan`

A list of `(timestamp_seconds, tempo_ratio)` points in the outgoing track's buffer-local time; empty means no time-stretching. `savings_until(t)` integrates how many seconds the stretch removes from the rendered stream up to input time `t`, going negative when the stretch *slows* the tail down. The bookkeeping has one non-obvious case the docstring calls out: rubberband initializes at the *first* step's ratio from `t=0`, so the span before the first step already runs stretched — a no-op for multi-step ramps whose first step is ratio 1.0, but not for single-step ones.

### `PlanMetrics` and vocal awareness

Vocal and energy awareness (#4816) is what most distinguishes the current engine. Vocal protections engage **per deck**: a track with a validated FireRed vocal-activity timeline gets its vocals protected, while one without is planned on energy facts alone — so a partially-analyzed library degrades per track rather than all-or-nothing.

`PlanMetrics` records the outcome, every field defaulting to its energy-only value:

| Field | Meaning |
|---|---|
| `strategy` | `ENERGY_ALIGNED` when a phrased candidate cleared the vocal-collision guard, `SHORT_VOCAL_HANDOFF` when every candidate collided and the equal-power fallback shipped |
| `audible_outgoing_trim` | Seconds of RMS-audible outgoing material dropped before the crossfade start |
| `outgoing_vocal_fade_seconds` | Outgoing vocal activity falling inside the rendered crossfade |
| `anchor_on_downbeat` | Whether the final `fade_out_window` landed on an outgoing downbeat |
| `collision_seconds` | Simultaneous outgoing/incoming vocal overlap |
| `weighted_collision_seconds` | The same, weighted by the crossfade curve's simultaneous-power integral |

The trim and downbeat facts are populated on every plan; the collision fields need *both* tracks to carry a validated vocal timeline and otherwise keep their defaults.

A related fix worth knowing about: an energy-drop transition could previously strand the listener in silence, because trimming to the audible boundary interacted badly with a quiet outgoing tail (#4926).

## The renderer

`TransitionRenderer.render(plan, pcm_format, fade_in_bytes_len)` is "the DJ's hands" — it picks tools from `filters.py` that realize the plan and produces the `CrossfadeTimingInfo` breakdown. It is the only place bytes re-enter: the plan is sized in seconds, and the renderer reconciles that against the actual buffer lengths, then drives both the overlap and the timing bookkeeping from that single reconciled value.

| Filter | Role |
|---|---|
| `CrossfadeFilter` | The overlap itself (FFmpeg `acrossfade`) |
| `GradualTimeStretchFilter` | Tempo ramp via rubberband |
| `FadeInTrimFilter` / `FadeOutTrimFilter` | Head and tail trims for beat alignment |
| `ShelfFilter` | Low/high shelf EQ for the band handover |
| `PeakFilter` | Peaking EQ with a bandwidth in octaves, for the mid/vocal handover |

`CrossfadeTimingInfo` breaks the output into `PRE | CF | POST` — pre-crossfade, crossfade, and post-crossfade durations plus any fade-in trim. The streaming layer needs this to split the mixer output correctly between the current response and the stored `CrossfadeData` for the next request, and lyrics sync reads it too.

`StandardCrossFade` shares the same `SmartFade` interface but needs none of the planner: `build()` clamps the overlap to fit the shorter input, quantizes it to a whole number of PCM frames, and emits a single `CrossfadeFilter`. The frame quantization is load-bearing rather than cosmetic — `apply()` slices buffers on frame boundaries, so a fractional overlap would leave the rendered buffer a fraction of a sample short of the `acrossfade` duration, and FFmpeg then silently produces **no output at all**.

## Key Files

| File | Role |
|---|---|
| [`mixer.py`](../../music_assistant/controllers/streams/smart_fades/mixer.py) | `SmartFadesMixer` — `build()` loads analysis and picks/primes the fade, `mix()` executes it |
| [`fades.py`](../../music_assistant/controllers/streams/smart_fades/fades.py) | `SmartFade` ABC, `SmartCrossFade` (planner + renderer), `StandardCrossFade`, FFmpeg `apply()` |
| [`models.py`](../../music_assistant/controllers/streams/smart_fades/models.py) | `TransitionPlan`, `TransitionTier`, `Deck`, `BandProfile`, `EqPlan`, `ShelfSchedule`, `TempoPlan`, `PlanMetrics`, `SmartFadeNotApplicable`, `BAND_RMS_BANDS` |
| [`planner/planner.py`](../../music_assistant/controllers/streams/smart_fades/planner/planner.py) | `TransitionPlanner` ABC and `SmartCrossFadePlanner` |
| [`planner/context.py`](../../music_assistant/controllers/streams/smart_fades/planner/context.py) | `TransitionContext` and `build_transition_context()` |
| [`planner/candidates.py`](../../music_assistant/controllers/streams/smart_fades/planner/candidates.py) | `CandidateSpec`, `Candidate`, `CandidateFactory`, generators |
| [`planner/policies.py`](../../music_assistant/controllers/streams/smart_fades/planner/policies.py) | `Policy`, `Verdict`, `default_policies()` |
| [`planner/selection.py`](../../music_assistant/controllers/streams/smart_fades/planner/selection.py) | `CandidateSelector`, `ScoredCandidate` |
| [`planner/assembly.py`](../../music_assistant/controllers/streams/smart_fades/planner/assembly.py) | `PlanAssembler`, `EmergencyHandoffFactory` |
| [`renderer.py`](../../music_assistant/controllers/streams/smart_fades/renderer.py) | `TransitionRenderer` |
| [`filters.py`](../../music_assistant/controllers/streams/smart_fades/filters.py) | Composable PCM filters |
| [`bands.py`](../../music_assistant/controllers/streams/smart_fades/bands.py) | Bar-level band-power statistics |
| [`structure.py`](../../music_assistant/controllers/streams/smart_fades/structure.py) | Fadeout and coda detection |
| [`vocal.py`](../../music_assistant/controllers/streams/smart_fades/vocal.py) | Vocal windows and collision scoring |
| [`helpers.py`](../../music_assistant/controllers/streams/smart_fades/helpers.py) | `SMART_CROSSFADE_DURATION`, tempo steps, downbeat extrapolation |
| [`providers/smart_fades/README.md`](../../music_assistant/providers/smart_fades/README.md) | The **analysis** provider's own design notes |

Driving PRs: #4532 (plan/render refactor), #4536 (bass swap), #4580 (analyzer v2 band envelopes and time signature), #4591 (content-aware 3-band EQ), #4786 (vocal activity detection), #4816 (vocal and energy aware planning), #4926 (energy-drop silence fix).

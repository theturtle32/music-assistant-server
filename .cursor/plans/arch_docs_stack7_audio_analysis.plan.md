---
name: arch_docs_stack7_audio_analysis
overview: "Add a new docs/architecture/16-audio-analysis.md covering the brand-new audio analysis subsystem (#3509 controller, #3636 smart fades v2, #3727 loudness migration, #3821 background scan, #3808 CPU throttle, #3703 robustness, #3687 cleanup, arousal field). Update 10-streaming-pipeline.md, README.md, and 00-overview.md to cross-reference the new file."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-audio-analysis from docs/architecture
    status: pending
  - id: implement
    content: Apply the doc edits per the pre-flight sub-plan (NEW FILE 16-audio-analysis.md + cross-refs)
    status: pending
  - id: verify
    content: pre-commit + sweep
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture
    status: pending
isProject: false
---

# Stack 7 — Audio analysis subsystem (NEW FILE)

## Scope (preliminary)

This is the largest brand-new subsystem and warrants a dedicated file.

- **New file [docs/architecture/16-audio-analysis.md](docs/architecture/16-audio-analysis.md):** Cover:
  - **Audio Analysis controller** (#3509) — [music_assistant/controllers/streams/audio_analysis.py](music_assistant/controllers/streams/audio_analysis.py).
  - **Audio Analysis provider model** — [music_assistant/models/audio_analysis_provider.py](music_assistant/models/audio_analysis_provider.py), [music_assistant/models/audio_analysis.py](music_assistant/models/audio_analysis.py).
  - **Smart fades v2 provider** (#3636) — the new `controllers/streams/smart_fades/` package (`fades.py`, `filters.py`, `helpers.py`, `mixer.py`, `__init__.py`).
  - **Loudness analyzer migration** (#3727) — was a separate analyzer, now an audio analysis provider.
  - **Background scan PCM streaming** (#3821).
  - **Version gating** (#1bf6a775).
  - **CPU throttle** (#3808) — torch capped at 25% CPU.
  - **Loudness measurement robustness** (#3703).
  - **Auto-cleanup on media item deletion** (#3687).
  - **`models/audio_analysis_provider.py` "arousal" field** (#132a0cac).
- **[docs/architecture/10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md):** Update the smart fades reference to point at the new package, remove the old `analyzer.py` references, and cross-link to `16-audio-analysis.md`.
- **[docs/architecture/README.md](docs/architecture/README.md):** Add the new entry to the table.
- **[docs/architecture/00-overview.md](docs/architecture/00-overview.md):** Add a one-line mention if the overview lists subsystems.

## Branch

Cut `docs/architecture-audio-analysis` from `docs/architecture` (independent — no parent).

```bash
git fetch origin
git checkout docs/architecture
git pull --ff-only origin docs/architecture
git checkout -b docs/architecture-audio-analysis
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

# Sub-plan 6: Final Convergence Review

**Scope**: Read all 16 architecture documents end-to-end as a unified corpus. Fix inconsistencies, fill gaps, normalize terminology, ensure cross-references are complete, and produce the `docs/architecture/README.md` index.

**Context**: Sub-plans 1-5 are complete. All 16 content documents exist under `docs/architecture/` (`00-overview.md` through `15-provider-lifecycle.md`). Each phase performed its own reconciliation with prior docs, so the corpus is already partially converged. This final pass reads everything with fresh eyes — no residual bias from having just written any of it.

**Model**: 1M context (must hold all 16 documents simultaneously for cross-referencing).

## What This Sub-plan Does NOT Do

- **No new exploration of the codebase.** All code exploration is complete. This is purely a review and editing pass over existing documents.
- **No structural rewrites.** If a document's organization is reasonable, leave it. Only fix factual errors, terminology, cross-references, and proportionality.
- **No expanding scope.** If a topic is deliberately omitted or deferred, don't add it.

## Deliverable

One new file plus edits to existing docs:

### `docs/architecture/README.md` — Getting Started and Documentation Catalog

A two-part document:

**Part 1 — Getting Started Orientation** (aim for ~1-2 pages):

A broad overview aimed at a developer encountering this codebase for the first time. Should answer: What is Music Assistant? What are the major moving pieces? How do they relate? What should I read first depending on what I want to work on?

Include:
- A brief "What is Music Assistant?" paragraph (not a repeat of `00-overview.md` — higher-level, more opinionated)
- A high-level architecture diagram (Mermaid) showing the major subsystems and how they connect — simpler and more abstract than any diagram in the individual docs
- **Recommended reading paths** based on what the developer wants to do:
  - "I want to build a music provider" → read X, Y, Z
  - "I want to build a player provider" → read A, B, C
  - "I want to understand player behavior and grouping" → read D, E, F
  - "I want to understand the streaming pipeline" → read G, H
  - "I want to build a plugin" → read I, J
  - "I want to understand the API" → read K, L
  - "I just want a complete picture" → read in document order (00 through 15)

**Part 2 — Complete Documentation Catalog**:

A table of contents covering ALL developer documentation, not just the new architecture docs:

- **Architecture docs** (`docs/architecture/`): All 16 documents with one-line descriptions
- **In-tree documentation**: Every existing doc discovered in the repo, organized by location:
  - Root: `CLAUDE.md`, `DEVELOPMENT.md`, `README.md`, `SECURITY.md`
  - Controllers: `controllers/streams/README.md`, `controllers/players/README.md`, `controllers/tasks/README.md`, `controllers/discovery/README.md`, `controllers/webserver/README.md`
  - Providers: `providers/spotify_connect/ARCHITECTURE.md`, `providers/sync_group/README.md`, `providers/universal_player/README.md`, `providers/sendspin/README.md`, `providers/airplay/README.md`, `providers/itunes_podcasts/README.md`, `providers/gpodder/README.md`
  - GitHub: `.github/copilot-instructions.md`, `.github/workflows/RELEASE_WORKFLOW_GUIDE.md`, `.github/workflows/RELEASE_NOTES_GENERATION.md`, `.github/actions/generate-release-notes/README.md`
  - Tests: `tests/providers/nicovideo/README.md`
- **External resources**: [developers.music-assistant.io](https://developers.music-assistant.io/), [music-assistant.io](https://music-assistant.io/) (especially the audio pipeline concept page)
- Brief notes on what each existing doc covers so a developer can tell at a glance whether it's relevant

## Convergence Review Checklist

Read all 16 documents in sequence (00 through 15). For each, check:

### 1. Terminology Consistency

Ensure the same concept uses the same term everywhere. Known risk areas:

- "sync leader" vs "group leader" vs "sync parent"
- "active source" vs "plugin source" vs "current source" vs "active_source"
- "group player" vs "SyncGroupPlayer" vs "UniversalGroupPlayer" vs "virtual group"
- "output protocol" vs "linked protocol" vs "protocol player"
- "flow mode" vs "queue flow stream" vs "continuous stream"
- "provider instance" vs "provider domain" vs "provider"
- "command handler" vs "API command" vs "JSON-RPC command"
- "playback state" vs "player state" vs "PlayerState"

If different docs use different terms for the same concept, pick the most precise one and standardize. Add a parenthetical on first use if the codebase itself uses multiple terms (e.g., "the sync leader (the `synced_to` target in the code)").

### 2. Cross-Reference Completeness

Every document that mentions a concept covered in another document should link to it. Check for:

- Forward references that were written as "see Sub-plan N" but not yet updated to actual links
- Concepts mentioned without links where a link would help (e.g., mentioning "volume normalization" in the player controller doc without linking to the streaming pipeline doc)
- Orphan documents that aren't referenced from anywhere else

### 3. Factual Consistency (No Contradictions)

If two documents describe the same mechanism, they must agree. Known areas to check:

- Group volume computation: does `07-volume.md` match `03-player-model.md`'s description of `group_volume`?
- Plugin volume callbacks: does `11-plugin-system.md` match `07-volume.md`'s description of `on_volume` and `in_use_by`?
- UGP streaming: does `06-grouping.md` match `10-streaming-pipeline.md`'s description of how UGP streams work?
- Protocol selection: does `05-protocol-linking.md` match `06-grouping.md`'s description of how sync groups select output protocols?
- Event types: does `01-event-system.md`'s event table match what other docs say about events emitted by their subsystems?
- Startup order: does `00-overview.md`'s lifecycle match what `15-provider-lifecycle.md`, `02-configuration.md`, and `13-discovery.md` say about when their subsystems initialize?
- Stream buffer timing: previous phases found the code uses 60s pre-buffer (not 30s as some docs claimed). Verify this is now consistent across `09-player-queues.md` and `10-streaming-pipeline.md`.

### 4. Proportional Depth

Are some docs over-detailed while others are too thin? The guide should feel balanced. Approximate target lengths:

- Core docs (00, 01, 02, 15): ~150-250 lines each
- Player docs (03, 04, 05): ~200-300 lines each
- Grouping/volume (06, 07): ~200-300 lines each
- Media/streaming (08, 09, 10): ~250-350 lines each
- Infrastructure (11, 12, 13, 14): ~150-300 lines each

If any doc is wildly out of proportion, note it but don't restructure — just trim obvious padding or add a missing section if it's brief to write.

### 5. Reading Flow

Can a developer read 00 through 15 in order and build understanding incrementally? Or does document 03 require concepts from document 06 that haven't been introduced yet? If so, add a brief inline note ("this is covered in detail in [06-grouping.md](06-grouping.md)") rather than reordering documents.

### 6. Stale Forward References

Search for any remaining instances of "Sub-plan" in the architecture docs — these are forward references that should have been replaced with actual links during reconciliation. Replace them all.

## Process

1. **Read all 16 documents** in order (00 through 15). Take notes on issues found.
2. **Fix all issues** found during the read-through. For each fix, make the minimal edit needed.
3. **Write `docs/architecture/README.md`** after completing the review, since the review may change document descriptions.
4. **Run `pre-commit run --all-files`** to ensure all edits pass linting.

## Output Format for README.md

- Use `#` for the title, `##` for Part 1 and Part 2
- The Mermaid diagram should be high-level (5-8 boxes max, showing the major subsystems)
- Reading paths should be bullet lists, not tables
- The documentation catalog should use tables with columns: Document, Description
- Keep the whole file under ~200 lines — it's an index, not a document

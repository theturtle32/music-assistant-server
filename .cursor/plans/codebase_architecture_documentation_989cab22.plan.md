---
name: Codebase Architecture Documentation
overview: Orchestrate 5 sub-plans that systematically explore the Music Assistant server codebase and produce a comprehensive developer architecture guide. Each sub-plan explores code fresh, writes docs, then reconciles with prior output — revising in both directions.
todos:
  - id: sp1-write
    content: Write Sub-plan 1 (Core Architecture) to docs/architecture/plans/sub-plan-1-core.md
    status: pending
  - id: sp1-exec
    content: Execute Sub-plan 1 [200k] — produce 00-overview.md, 01-event-system.md, 02-configuration.md, 15-provider-lifecycle.md
    status: pending
  - id: sp2-write
    content: Write Sub-plan 2 (Player Model and Controller) to docs/architecture/plans/sub-plan-2-player.md
    status: pending
  - id: sp2-exec
    content: Execute Sub-plan 2 [200k] — produce 03-player-model.md, 04-player-controller.md, 05-protocol-linking.md; reconcile with Sub-plan 1 docs
    status: pending
  - id: sp3-write
    content: Write Sub-plan 3 (Grouping and Volume) to docs/architecture/plans/sub-plan-3-grouping-volume.md
    status: pending
  - id: sp3-exec
    content: Execute Sub-plan 3 [1M] — produce 06-grouping.md, 07-volume.md; reconcile with Sub-plan 1-2 docs (deepest cross-cutting concerns)
    status: pending
  - id: sp4-write
    content: Write Sub-plan 4 (Media, Queues, Streaming) to docs/architecture/plans/sub-plan-4-media-streaming.md
    status: pending
  - id: sp4-exec
    content: Execute Sub-plan 4 [200k] — produce 08-media-library.md, 09-player-queues.md, 10-streaming-pipeline.md; reconcile with prior docs
    status: pending
  - id: sp5-write
    content: Write Sub-plan 5 (Plugins, Infrastructure, Final Review) to docs/architecture/plans/sub-plan-5-plugins-infra.md
    status: pending
  - id: sp5-exec
    content: Execute Sub-plan 5 [1M] — produce 11-plugin-system.md, 12-webserver-api.md, 13-discovery.md, 14-metadata.md; full convergence review of all docs
    status: pending
isProject: false
---

# Music Assistant Server — Architecture Documentation Orchestration Plan

This is the **master plan**. It does not contain the exploration or writing work itself — that lives in 5 sub-plans, each saved as a markdown file and executed in a dedicated conversation with fresh context. This plan's job is to define the sub-plans, their sequencing, their deliverables, and the reconciliation loop between them.

## Manual Coordination Workflow

Execution requires manual coordination between Plan mode and Agent mode in Cursor. Each sub-plan has two steps:

**Step 1 — Write the sub-plan (Plan mode).** Open a conversation with this master plan visible. Ask for the next sub-plan to be written. Review the resulting markdown file and request adjustments if needed.

**Step 2 — Execute the sub-plan (Agent mode, new conversation).** Start a **new conversation** in Agent mode. Select the recommended model for that phase (see table). Reference the sub-plan file (e.g., `@docs/architecture/plans/sub-plan-1-core.md`) and ask for it to be executed. The fresh conversation gives the agent clean context for independent exploration.

**Between phases:** Return to the master plan (Plan mode) to write the next sub-plan. This is the opportunity to adjust scope based on what prior phases discovered.

**Execution sequence:**

- Phase 1 write — Plan mode, any model — Write `sub-plan-1-core.md`
- Phase 1 exec — Agent mode, **200k model** — Produce `00-overview.md`, `01-event-system.md`, `02-configuration.md`, `15-provider-lifecycle.md`
- Phase 2 write — Plan mode, any model — Write `sub-plan-2-player.md`
- Phase 2 exec — Agent mode, **200k model** — Produce `03-player-model.md`, `04-player-controller.md`, `05-protocol-linking.md`; reconcile with phase 1
- Phase 3 write — Plan mode, any model — Write `sub-plan-3-grouping-volume.md`
- Phase 3 exec — Agent mode, **1M model** — Produce `06-grouping.md`, `07-volume.md`; reconcile with phases 1-2
- Phase 4 write — Plan mode, any model — Write `sub-plan-4-media-streaming.md`
- Phase 4 exec — Agent mode, **200k model** — Produce `08-media-library.md`, `09-player-queues.md`, `10-streaming-pipeline.md`; reconcile with phases 1-3
- Phase 5 write — Plan mode, any model — Write `sub-plan-5-plugins-infra.md`
- Phase 5 exec — Agent mode, **1M model** — Produce `11-plugin-system.md`, `12-webserver-api.md`, `13-discovery.md`, `14-metadata.md`; full convergence review

## Context

The Music Assistant server has ~494 Python files across 79 providers, 10+ controllers, and 9 model files. Existing documentation is scattered across in-tree READMEs (streams, players, tasks, discovery, webserver, sync group, spotify connect), DEVELOPMENT.md, CLAUDE.md, and the external [developers.music-assistant.io](https://developers.music-assistant.io/). Major gaps exist in the player model internals, media controllers, plugin architecture, event system, configuration, and cross-cutting concerns like grouping and volume.

## Output

A set of 16 markdown documents under `docs/architecture/` in the fork, plus a lightweight index. Each document covers one subsystem or cross-cutting concern, written to be useful to a developer (including this project's contributor) who wants to understand the codebase deeply before making changes.

Sub-plans are saved to `docs/architecture/plans/` for reference and traceability.

## Process Model: Convergent Iteration, Not a DAG

Understanding a codebase is not a linear pipeline. Later phases routinely recontextualize what was learned in earlier phases, and that recontextualization can flow in both directions — a later phase may discover that an earlier doc was wrong, but reading the earlier doc may also reveal that the later phase's own understanding was incomplete. The dependencies between subsystems form cycles, not a DAG.

The process handles this through **convergent iteration**:

1. Each sub-plan explores its own domain **fresh from the code**, without reading prior docs first. This prevents inheriting wrong assumptions.
2. After forming its own independent understanding and writing its own docs, the sub-plan reads prior output for **reconciliation** — a bidirectional comparison.
3. Reconciliation may revise prior docs (correcting errors found with new understanding), revise the current phase's own docs (recontextualized by what prior phases captured), or both.
4. If reconciliation produces significant rewrites of the current phase's output, the agent re-examines whether those rewrites cascade into further changes to prior docs.
5. The process converges when Sub-plan 5's final review pass reads all documents end-to-end and finds no meaningful contradictions.

**What each sub-plan reads from prior output:**

- **Structural vocabulary only** at the start (section headings, class/method names, terminology — enough to not waste time rediscovering basics)
- **Full content** only after its own exploration and writing is complete, during the reconciliation step

## Model Selection Guidance

Each sub-plan specifies a recommended context window size:

- **200k context**: Preferred for focused, bounded subsystems. The smaller window keeps the model sharper and more cost-effective. Use for sub-plans where the source files fit comfortably and cross-cutting concerns are limited.
- **1M context**: Reserved for sub-plans that must hold many large files simultaneously AND read/reconcile multiple prior documents. The tradeoff is slightly less focused reasoning, but the ability to see everything at once prevents the "losing earlier context" problem that would otherwise force incomplete reconciliation.

## Writing Principles (shared across all sub-plans)

- **Cite code, not assumptions**: Every claim backed by specific file + method name (line numbers go stale, so prefer method/class names)
- **Explain the "why"**: Not just what the code does, but why it is structured that way — from git history, PRs, maintainer comments
- **Flag known gaps honestly**: Where the architecture has recognized rough edges, note them as known limitations rather than proposing fixes
- **Keep it skimmable**: Mermaid diagrams for flows, tables for comparisons, code snippets kept short
- **Human voice**: Written to be presentable to maintainers — no AI-generated filler, no over-explanation of obvious things

## Key Resources

**Repositories** (the server exists within a 38-repo ecosystem under the music-assistant org):

- **Server repo**: [music-assistant/server](https://github.com/music-assistant/server) (branch: `dev`) — the primary focus of this documentation effort
- **Models package**: [music-assistant/models](https://github.com/music-assistant/models) — shared data models (mashumaro for dataclass serialization, orjson for JSON), used by both server and client; defines `EventType`, `MediaType`, `PlayerFeature`, `StreamDetails`, `ProviderFeature`, etc.; `API_SCHEMA_VERSION` gates client-server compatibility
- **Client library**: [music-assistant/client](https://github.com/music-assistant/client) — async Python client with controllers mirroring the server's; its README documents authentication flows and the event subscription pattern from the consumer side; useful as a research resource when documenting the API and event system
- **Support/issues/discussions**: [music-assistant/support](https://github.com/music-assistant/support)
- **Audio protocol libraries**: `aioslimproto`, `aiosonos`, `cliairplay`, and others — low-level protocol implementations consumed by player providers

**Documentation sites**:

- **Developer docs**: [developers.music-assistant.io](https://developers.music-assistant.io/) — single page, mirrors DEVELOPMENT.md
- **End-user docs**: [music-assistant.io](https://music-assistant.io/) — comprehensive user guide; the [audio pipeline](https://music-assistant.io/music-assistant-concepts/audio/) and tech info FAQ pages carry architectural value (PCM processing, volume normalization, flow mode, output formats)
- **Auto-generated API docs**: Available at `http://SERVER:8095/api-docs` on a running instance (since v2.7.0) — not published publicly but useful during Sub-plan 5 exploration

**Existing in-tree docs**:

- `controllers/streams/README.md`, `controllers/players/README.md`, `controllers/tasks/README.md`, `controllers/discovery/README.md`, `controllers/webserver/README.md`
- `providers/spotify_connect/ARCHITECTURE.md`, `providers/sync_group/README.md`
- `CLAUDE.md`, `DEVELOPMENT.md`

**Prior PRs with maintainer feedback**: [#3399](https://github.com/music-assistant/server/pull/3399), [#3512](https://github.com/music-assistant/server/pull/3512), [#3534](https://github.com/music-assistant/server/pull/3534)

**Community**: [Discord](https://discord.gg/kaVm8hGpne) (~5k members, `#dev` channel for architectural discussions) — the maintainer's preferred venue for design conversations

---

## Sub-plan 1: Core Architecture

**File**: `docs/architecture/plans/sub-plan-1-core.md`
**Model**: 200k context (bounded scope, moderate file sizes, no prior output to reconcile)

**Scope**: The foundation that everything else builds on — server lifecycle, event system, configuration/persistence, and provider lifecycle.

**Deliverables**:

- `docs/architecture/00-overview.md` — High-level architecture, component map, startup/shutdown lifecycle, and the multi-repo ecosystem (models package, client library, frontend, protocol libraries — situate the server within the broader 38-repo org)
- `docs/architecture/01-event-system.md` — EventType enum, signal_event/subscribe, sync vs async subscribers, thread safety
- `docs/architecture/02-configuration.md` — Config hierarchy, player/provider config, SQLite databases, cache
- `docs/architecture/15-provider-lifecycle.md` — How providers load, configure, discover, and integrate

**Key files to explore**:

- `mass.py`, `__main__.py`, `models/core_controller.py`, `models/provider.py`
- `controllers/config.py`, `controllers/cache.py`, `helpers/database.py`
- `constants.py` (config keys, DB tables, defaults)
- `music_assistant_models` package (EventType, MassEvent — installed dependency; uses mashumaro for dataclass serialization, orjson for JSON; `API_SCHEMA_VERSION` gates client-server compatibility)
- The `music-assistant/client` library README — documents the event subscription and command patterns from the consumer side

**Key questions**:

- Startup order and why it matters (parallel TaskGroup setup vs sequential post_setup)
- `command_handlers` (imperative API) vs `signal_event` (pub/sub) — when to use which
- Safe mode: what loads, what doesn't, why
- CoreConfig / PlayerConfig / ProviderConfig hierarchy
- SQLite schema management — cache DB vs config storage vs auth DB
- Provider manifest discovery, module loading, `handle_async_init`, `loaded_in_mass`

**Research**:

- Git history on `mass.py` for lifecycle refactors
- `music_assistant_models` repo for EventType definitions
- How `CONFIGURABLE_CORE_CONTROLLERS` relates to provider manifests

**Reconciliation**: N/A (first sub-plan — no prior output exists)

---

## Sub-plan 2: Player Model and Controller

**File**: `docs/architecture/plans/sub-plan-2-player.md`
**Model**: 200k context (large files but focused domain; reconciliation is lightweight since only Sub-plan 1 exists)

**Scope**: The Player abstraction (the most complex model in the system), the PlayerController command surface, and protocol linking.

**Deliverables**:

- `docs/architecture/03-player-model.md` — Player ABC, *attr* pattern, PlayerState snapshot, PlayerType taxonomy, _*final* computed properties, PlayerFeature flags
- `docs/architecture/04-player-controller.md` — Command routing, *handle_cmd* vs cmd_ methods, redirects, power management, registration
- `docs/architecture/05-protocol-linking.md` — Multi-protocol device merging, identifier hierarchy, output protocol selection

**Key files to explore**:

- `models/player.py` (2154 lines), `models/player_provider.py`
- `controllers/players/controller.py` (3736 lines), `controllers/players/helpers.py`
- `controllers/players/protocol_linking.py`, `controllers/players/README.md`

**Key questions**:

- The `_attr_` pattern — modeled after Home Assistant entities? Confirm via git history
- `Player` (runtime, mutable) vs `PlayerState` (API snapshot, from models package) — how `state` property composes the effective view
- `__final_`* properties: what overrides what, and why some are config-driven vs provider-driven
- PlayerType taxonomy: PLAYER, PROTOCOL, GROUP, STEREO_PAIR — what each means, what code paths branch on type
- `_get_player_with_redirect` — the central command routing mechanism
- Public `cmd_`*(permission checks, logging, power-on-demand) vs private `_handle_cmd_`* (actual work)
- Protocol linking: what problem it solves, the identifier matching hierarchy (MAC > serial > UUID > ... > IP > player_id), why GROUP/STEREO_PAIR are excluded, `_select_best_output_protocol`

**Research**:

- PRs touching protocol linking: #3294, #3284, #3300
- The players/README.md (already thorough — verify against code, incorporate rather than duplicate)
- `_attr`_ pattern origin in git history

**Reconciliation with Sub-plan 1**:

Step 1 (before exploring): Skim only the section headings and key terms from `00-overview.md` and `15-provider-lifecycle.md` for structural vocabulary (controller names, startup order, registration method names). Do not read interpretive content.

Step 2 (after writing own docs): Read Sub-plan 1 docs in full. Compare independently formed understanding against their claims. Specific checks:

- Does `00-overview.md` accurately describe how the PlayerController fits into the startup lifecycle?
- Does `15-provider-lifecycle.md` correctly describe how PlayerProvider discovery and registration works?
- Does anything in Sub-plan 1's docs contradict what was learned from reading the player code directly?

Step 3 (bidirectional revision): Fix errors in Sub-plan 1 docs. Also check: does Sub-plan 1's description of the event system or config system recontextualize anything about how the player model works (e.g., how PlayerConfig interacts with the config controller, how player state changes emit events)? If so, revise own docs too.

Step 4 (cascade check): If own docs were significantly revised in Step 3, re-read the revisions to Sub-plan 1 docs and confirm they are still consistent.

---

## Sub-plan 3: Grouping and Volume

**File**: `docs/architecture/plans/sub-plan-3-grouping-volume.md`
**Model**: 1M context (highest cross-cutting complexity in the project; must hold sync_group provider, universal_group provider, large sections of player controller AND player model simultaneously, plus reconcile against 6 prior documents across 2 sub-plans; this is the area where our PRs had the most misunderstandings)

**Scope**: The three grouping models (sync groups, universal groups, ad-hoc sync), group volume control, and plugin volume callbacks. This is the area where our prior PRs had the most misunderstandings — extra care needed.

**Deliverables**:

- `docs/architecture/06-grouping.md` — Sync groups, universal groups, ad-hoc sync, membership, form/dissolve lifecycle, sync leader selection, dynamic vs static
- `docs/architecture/07-volume.md` — Individual and group volume, additive-delta algorithm, plugin callbacks, feedback loop problem, known issues

**Key files to explore**:

- `providers/sync_group/` (player.py, provider.py, README.md)
- `providers/universal_group/` (player.py, ugp_stream.py, provider.py — no README)
- `controllers/players/controller.py` (group-related methods: cmd_set_members, cmd_group, cmd_ungroup, cmd_group_volume, set_group_volume, iter_group_members, _get_player_groups,_handle_set_members, _handle_set_members_with_protocols)
- `models/player.py` (group_volume, group_members, synced_to, active_group, __final_group_members,__final_synced_to)
- `models/plugin.py` (PluginSource.on_volume, in_use_by)

**Key questions**:

- Three grouping models: when each applies, how they differ architecturally
  - **Sync group**: vendor multi-room via SyncGroupPlayer + sync leader delegation
  - **Universal group**: MA server-side mixing via UGP flow stream to each member independently
  - **Ad-hoc sync**: direct set_members on a physical player without a SyncGroupPlayer wrapper
- `active_group` vs `synced_to` vs `group_members` — three different relationships, often confused
- `_resolve_group_data_owner` — why it exists, what "canonical data owner" means
- Volume: the additive-delta algorithm in `set_group_volume`, its clamping/drift behavior, why the maintainer considers this acceptable
- Plugin volume callbacks: `_handle_volume_plugin_callback`, `_get_active_plugin_source`, the `in_use_by` gap for groups
- The feedback loop: how per-child `on_volume` callbacks cause oscillation with plugins like Spotify Connect

**Research**:

- PRs #3534 (select_source ungroup), #3343 (Cast + sync groups), #3460 (protocol ID migration), #3277 (volume_up/down for groups), #3399 and #3512 (our PRs — maintainer feedback is the most important data here)
- sync_group/README.md (already detailed)
- Search support discussions for group-related feature requests

**Reconciliation with Sub-plan 1-2** (this is the most important reconciliation pass — grouping touches almost everything):

Step 1 (before exploring): Skim section headings and terminology from all 6 prior docs. Note the vocabulary used for PlayerType, group_members, synced_to, command routing, events. Do not read interpretive claims about how grouping works.

Step 2 (after writing own docs): Read all 6 prior documents in full. This is the highest-risk reconciliation because grouping is the most cross-cutting concern. Specific checks:

- Does `03-player-model.md` accurately describe `group_members`, `synced_to`, `active_group`, `group_volume`? These properties have subtle semantics that are only fully clear after understanding the three grouping models. Expect to find corrections needed here.
- Does `04-player-controller.md` correctly describe group-related command routing? Does it need forward references to `06-grouping.md`?
- Does `05-protocol-linking.md` correctly describe the interaction between protocol linking and grouping (e.g., `_handle_set_members_with_protocols`)?
- Does `15-provider-lifecycle.md` mention SyncGroupProvider and UniversalGroupProvider as builtin provider types?
- Does `01-event-system.md` cover the events that drive group state changes?

Step 3 (bidirectional revision): Fix errors in prior docs. Then critically: do the prior docs' descriptions of event propagation, config persistence, or command routing recontextualize how grouping or volume actually works? For example:

- If `02-configuration.md` describes how player config is persisted, does that change the understanding of where group volume state lives?
- If `04-player-controller.md` describes `_get_player_with_redirect`, does that change the understanding of how commands reach group players?
If so, revise `06-grouping.md` and `07-volume.md` accordingly.

Step 4 (cascade check): Re-read all revisions (both directions) and confirm internal consistency. If revising `03-player-model.md` changed something that `04-player-controller.md` depends on, verify the controller doc is still correct.

---

## Sub-plan 4: Media, Queues, and Streaming

**File**: `docs/architecture/plans/sub-plan-4-media-streaming.md`
**Model**: 200k context (mostly self-contained subsystems; the streams controller has thorough existing docs to verify against; reconciliation with prior docs is moderate)

**Scope**: The music library, media types, player queues, and the audio streaming pipeline.

**Deliverables**:

- `docs/architecture/08-media-library.md` — Music controller, media types, library sync, URI resolution, provider orchestration
- `docs/architecture/09-player-queues.md` — Queue management, playback orchestration, relationship to players and streams
- `docs/architecture/10-streaming-pipeline.md` — Audio pipeline end-to-end, FFmpeg, AudioBuffer, smart fades, DSP

**Key files to explore**:

- `controllers/music.py`, `controllers/media/` (base.py + each media type controller)
- `models/music_provider.py` (provider interface for music sources)
- `controllers/player_queues.py`
- `controllers/streams/` (all files), `controllers/streams/README.md`
- `helpers/audio.py`, `helpers/ffmpeg.py`

**Key questions**:

- How library sync works — provider iteration, deduplication, matching
- MediaType hierarchy and the shared `music_assistant_models` types
- URI resolution: how `uri://provider/item_id` is parsed and resolved
- Queue as "usual active source" — how it relates to PluginSource and other active sources
- The stream pipeline: provider -> FFmpeg -> AudioBuffer -> normalize -> smart fades -> encode -> HTTP
- AudioBuffer types (SEEKABLE vs ROLLING) and when each is used
- Smart fades: beat detection, crossfade, gapless transitions
- DSP chain and per-player output format

**Research**:

- streams/README.md (thorough — verify and cross-reference)
- Git history on player_queues.py for recent refactors
- How `get_stream_details` and `get_audio_stream` work across providers

**Reconciliation with Sub-plan 1-3**:

Step 1 (before exploring): Skim headings/terms from prior docs. Key vocabulary to pick up: how the event system works (for queue events), how player commands route (for play/pause/next), how groups interact with streams (for UGP).

Step 2 (after writing own docs): Read prior docs in full. Specific checks:

- Does `00-overview.md` adequately introduce the media/streaming layer?
- Does `04-player-controller.md` need updates now that we understand how queues and streams interact with players? The queue is the "usual active source" — does the controller doc explain what that means?
- Does `06-grouping.md` need to explain how UGP streaming works, since the flow-mode HTTP stream is central to universal groups?
- Does `15-provider-lifecycle.md` cover how music providers register and how their `get_stream_details`/`get_audio_stream` are called?

Step 3 (bidirectional revision): Fix errors in prior docs. Check if prior docs recontextualize streaming — e.g., if `06-grouping.md`'s description of UGP reveals that the streaming pipeline doc needs to distinguish between normal streams and UGP streams.

Step 4 (cascade check): If UGP streaming details were added to `06-grouping.md`, verify they are consistent with what `10-streaming-pipeline.md` says about the same mechanism.

---

## Sub-plan 5: Plugins, Infrastructure, and Final Convergence

**File**: `docs/architecture/plans/sub-plan-5-plugins-infra.md`
**Model**: 1M context (must write 4 new docs AND read all 12 prior documents for final convergence review; the plugin system touches players, groups, volume, and streaming simultaneously; webserver/API touches events, config, and command routing)

**Scope**: Plugin system, webserver/API, discovery, metadata, and a final convergence pass across all 16 documents.

**Deliverables**:

- `docs/architecture/11-plugin-system.md` — PluginSource, callbacks, in_use_by, receiver vs scrobbler plugins, Spotify Connect as exemplar
- `docs/architecture/12-webserver-api.md` — JSON-RPC command model, @api_command, WebSocket, auth, remote access
- `docs/architecture/13-discovery.md` — mDNS/SSDP, provider integration, Zeroconf
- `docs/architecture/14-metadata.md` — Metadata enrichment, provider priority, image proxy
- Updated versions of any prior docs that need corrections
- `docs/architecture/README.md` — **Two-part document** (see details below):
  1. A broad getting-started orientation for developers new to the codebase
  2. A complete catalog of all documentation (both the new architecture docs and all existing in-tree docs)

**Key files to explore**:

- `models/plugin.py`, `providers/_demo_plugin_provider/`, receiver plugins (airplay_receiver, spotify_connect, ariacast_receiver, vban_receiver), scrobbler plugins (lastfm_scrobble, listenbrainz_scrobble)
- `providers/spotify_connect/` (all files, ARCHITECTURE.md)
- `controllers/webserver/` (all files), `controllers/webserver/README.md`
- `controllers/discovery/controller.py`, `controllers/discovery/README.md`
- `controllers/metadata.py`, metadata providers

**Key questions**:

- PluginSource callbacks (on_play, on_pause, on_volume, etc.) and how they bridge external apps to MA players
- `in_use_by` semantics — always physical player ID, not group (known gap, now partially addressed by #3534)
- `StreamType.CUSTOM` vs URL-based sources
- Spotify Connect as exemplar: librespot subprocess, event webservice, multi-instance, credential flow
- JSON-RPC command model and the `@api_command` decorator
- WebSocket subscription model for live UI updates
- Auth: bcrypt, token types, HA OAuth integration, remote access WebRTC
- Discovery: shared Zeroconf instance, manifest-driven subscriptions, replay on provider load

**Research**:

- spotify_connect/ARCHITECTURE.md and webserver/README.md (both detailed — verify against code)
- discovery/README.md
- Git history on plugin.py for `in_use_by` evolution

**Reconciliation with Sub-plan 1-4** (same explore-first protocol as earlier phases):

Step 1 (before exploring): Skim headings/terms from all 12 prior docs.

Step 2 (after writing own docs): Read all prior docs. The plugin system is especially likely to reveal gaps in prior docs:

- `07-volume.md` describes the plugin volume feedback loop — does the plugin system doc's description of `PluginSource.on_volume` and `in_use_by` contradict or refine anything there?
- `04-player-controller.md` describes `select_source` — does the plugin doc's description of how plugins register as active sources add nuance?
- `01-event-system.md` describes the event bus — does the webserver doc reveal that some communication patterns (like JSON-RPC commands) bypass events entirely?

Step 3 (bidirectional revision): Fix errors in both directions.

**Final convergence review** (the last step of the entire project):

Read all 16 documents end-to-end as a unified corpus. This is not a per-document check — it is a reading of the whole guide as a developer would encounter it. Check for:

- **Terminology consistency**: "sync leader" vs "group leader", "active source" vs "plugin source" vs "current source", "group player" vs "SyncGroupPlayer" vs "virtual group"
- **Cross-reference completeness**: Every document that mentions a concept covered in another document should link to it
- **No contradictions**: If `07-volume.md` says "group volume is derived from child averages" but `03-player-model.md` says "group volume reads from stored state", one of them is wrong
- **Proportional depth**: Are some docs over-detailed while others are too thin? Does the guide feel balanced?
- **Forward/backward flow**: Can a developer read 00 through 15 in order and build understanding incrementally? Or does document 03 require concepts from document 06?
- Produce `docs/architecture/README.md` as a two-part document:

**Part 1 — Getting Started Orientation**: A broad overview aimed at a developer encountering this codebase for the first time. Should answer: What is Music Assistant? What are the major moving pieces? How do they relate? What should I read first depending on what I want to work on? This is NOT a repeat of `00-overview.md` — it is higher-level and more opinionated, with a "recommended reading paths" section (e.g., "If you want to build a music provider, read X then Y. If you want to understand player behavior, start with Z."). Include a high-level architecture diagram.

**Part 2 — Complete Documentation Catalog**: A table of contents that covers ALL developer documentation, not just our new architecture docs. This includes:

- The 16 new `docs/architecture/` documents with one-line descriptions
- All existing in-tree documentation: `CLAUDE.md`, `DEVELOPMENT.md`, `controllers/streams/README.md`, `controllers/players/README.md`, `controllers/tasks/README.md`, `controllers/discovery/README.md`, `controllers/webserver/README.md`, `providers/spotify_connect/ARCHITECTURE.md`, `providers/sync_group/README.md`, `.github/copilot-instructions.md`, `.github/workflows/RELEASE_WORKFLOW_GUIDE.md`, `.github/workflows/RELEASE_NOTES_GENERATION.md`, and any other docs discovered during exploration
- The external [developers.music-assistant.io](https://developers.music-assistant.io/) site
- Brief notes on what each existing doc covers and when it was last meaningfully updated, so a developer can tell at a glance whether a doc is current or potentially stale

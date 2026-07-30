---
name: arch_docs_v2_phase13_ai_and_mcp
overview: Phase 13. Create a new 18-ai-and-mcp.md documenting the AI_QUERY/TTS provider-feature pattern, the Home Assistant plugin as reference implementer, AI Radio as orchestrator, Music Quiz and Smart Playlist as consumers, and the FastMCP server as the external-agent surface. Add the missing plugin ecosystem sections and shared playback to 11-plugin-system.md.
todos:
  - id: preflight
    content: "Pre-flight: verify the AI_QUERY/TTS feature surface, ai_radio runtime, fastmcp_server tool namespaces, and shared playback against the working tree"
    status: completed
  - id: newdoc_pattern
    content: Create docs/architecture/18-ai-and-mcp.md with the AI_QUERY/TTS provider-feature pattern and the deliberate absence of a central AI abstraction
    status: completed
  - id: newdoc_hass
    content: "18-ai-and-mcp.md: document the hass plugin as the reference AI/TTS backend"
    status: completed
  - id: newdoc_airadio
    content: "18-ai-and-mcp.md: document AI Radio as orchestrator"
    status: completed
  - id: newdoc_consumers
    content: "18-ai-and-mcp.md: document Music Quiz and Smart Playlist as AI consumers"
    status: completed
  - id: newdoc_mcp
    content: "18-ai-and-mcp.md: document the FastMCP server as the inverse surface (MA exposed to external agents)"
    status: completed
  - id: shared_playback
    content: "11-plugin-system.md: add a shared playback sessions section for helpers/shared_playback.py"
    status: completed
  - id: ecosystem
    content: "11-plugin-system.md: add the missing ecosystem plugin sections (music_quiz, sonic_similarity, smart_playlist, radio_playlist, hue_entertainment, profiler, plex_connect, hass)"
    status: completed
  - id: tts
    content: Verify the TTS and announcement flow and update wherever it is documented
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 13 — AI, MCP, and the plugin ecosystem

New file `docs/architecture/18-ai-and-mcp.md`, plus additive sections in
`docs/architecture/11-plugin-system.md`. Depends on Phase 12 having landed the core model rewrite.

## Why a separate doc

AI shows up in three architecturally distinct places and is easy to conflate:

1. MA **consuming** an LLM through a provider feature (`ProviderFeature.AI_QUERY`,
   `ProviderFeature.TTS`).
2. MA **orchestrating** AI-driven listening experiences (AI Radio, Music Quiz).
3. MA **being exposed to** external LLM agents (the FastMCP server).

Keeping receiver and control mechanics in `11-plugin-system.md` and putting this cluster in its own
file keeps both readable.

## `18-ai-and-mcp.md`

### The provider-feature pattern

The most important architectural point: **there is no central `mass.ai` abstraction.** Consumers
call `mass.get_providers_supporting_feature(ProviderFeature.AI_QUERY)` and invoke
`plugin.ai_query()` on whatever is configured. Same shape for `ProviderFeature.TTS` and
`get_tts_message`. Document the contract of both hooks (they live on `PluginProvider` in
`models/plugin.py`), the fact that they are optional and feature-gated, and what a consumer can and
cannot assume about latency or availability.

### `hass` as reference implementer

The Home Assistant plugin dynamically declares `TTS` and `AI_QUERY` when the corresponding HA
entities are configured, backing them with HA's `ai_task` and TTS entities. It is both a bridge and
the primary AI backend, which is worth stating plainly since nothing in the name suggests it.

### AI Radio (#3407)

An alpha orchestrator plugin for AI-moderated radio stations and dynamic queue generation.
`SUPPORTED_FEATURES` is empty — it is purely a consumer. Read
`music_assistant/providers/ai_radio/runtime.py` and document the station/moderator model, how it
interacts with dynamic playlists (cross-link Phase 7), and how TTS moderator segments enter the
audio path.

### Consumers

- **Music Quiz** (#4572): experimental multiplayer quiz (guess-the-song, timeline, trivia) using
  `SharedPlaybackSession` venue and remote modes, with trivia and distractors from `AI_QUERY`
  providers.
- **Smart Playlist** (#3630): rule-based dynamic playlists with optional AI-generated descriptions.

### FastMCP server — the inverse surface

`providers/fastmcp_server/` mounts an MCP server on the MA webserver at `/mcp/v1/*` via an ASGI
bridge, exposing library, queue, playback, players, playlists, volume, media, metadata, debug, and
config tool namespaces to external LLM clients. Optional auth uses MA tokens, with RFC 9728
`/.well-known/oauth-protected-resource` advertisement, plus a Connect Wizard.

Driving PRs: #3858, #4019, #4486, #4771, #4833.

Cross-link Phase 14 for the auth model and the webserver route map; this doc should own the tool
surface and the agent-facing design, not the token mechanics.

## `11-plugin-system.md` additions

### Shared playback sessions

`music_assistant/helpers/shared_playback.py` (#4672) underpins Party and Music Quiz with `VENUE`
(a real player) and `REMOTE` (Sendspin virtual player) modes. Document how a session relates to
queue ownership and guest access, and cross-link Phase 14 for guest tokens and join codes.

### Ecosystem plugin sections

Short sections — one to three paragraphs each, with declared `ProviderFeature`s stated explicitly:

| Plugin | Category | Features |
| --- | --- | --- |
| `music_quiz` | guest/social | none; uses `SharedPlaybackSession` + `AI_QUERY` |
| `sonic_similarity` (#3943) | similarity engine | `SIMILAR_TRACKS`, `RECOMMENDATIONS`, optional `SEARCH` |
| `smart_playlist` (#3630) | dynamic playlists | `BROWSE`, `RECOMMENDATIONS` |
| `radio_playlist` | virtual radio playlists | none; implements `get_playlist` |
| `hue_entertainment` (#4042, #4152) | light sync / visualizer | none; `depends_on: sendspin` |
| `profiler` | diagnostics | none; `profiler/report` API |
| `plex_connect` (#3510) | external control bridge | none |
| `hass` | HA bridge + AI/TTS backend | dynamic `TTS`, `AI_QUERY` |

For `sonic_similarity` cross-link Phase 9 (it consumes sonic_analysis and smart_fades output);
`hue_entertainment` also consumes persisted analysis. For `hue_entertainment` and `profiler`, link
to their in-tree READMEs rather than restating them.

## TTS and announcements

Verify whether the TTS and announcement flow changed, and update wherever it is currently
documented (check `04-player-controller.md` and `10-streaming-pipeline.md` for announcement text).
`get_tts_message` still exists; confirm the announcement path around it.

## Verification

- `rg "ProviderFeature.AI_QUERY|ProviderFeature.TTS|get_providers_supporting_feature|ai_query|get_tts_message"`.
- `rg "SharedPlaybackSession"` and confirm the venue/remote mode names.
- Confirm the MCP mount path and tool namespaces directly from `providers/fastmcp_server/`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): add AI and MCP doc, plugin ecosystem and shared playback sections

Phase 13 of the upstream/dev refresh.
```

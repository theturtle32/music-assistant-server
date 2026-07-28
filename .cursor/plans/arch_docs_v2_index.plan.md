---
name: arch_docs_v2_index
overview: "INDEX (no todos). Master overview for the second architecture-docs refresh: bringing docs/architecture up to date with the 1096 upstream/dev commits landed since the first refresh, plus fixing stale upstream in-tree README.md files. Links to 17 sequential phase plans, each independently buildable as one commit on a single long-lived branch."
todos: []
isProject: false
---

# Architecture docs refresh, round 2 — master index

## Why

The `docs/architecture` branch is based on upstream commit `4b67568d6` (May 2026). Upstream
`dev` is now at `76422b305`, **1096 commits ahead**, with 1217 files changed
(+183,340 / −58,301). Four monolithic controllers became packages, two core abstractions the
docs are built around were replaced outright, API authorization was redesigned, and roughly a
dozen genuinely new subsystems have no documentation at all.

This index tracks the work to make `docs/architecture` an accurate description of
current `upstream/dev`, so that PR #6 (`docs/architecture` → `dev`) can be submitted upstream.

## Headline changes driving the work

| Change | Upstream PR | Doc impact |
| --- | --- | --- |
| `PluginSource` replaced by first-class `AudioSource` MediaItems | #3938 | Invalidates most of `11-plugin-system.md`, plugin sections of `07-volume.md` |
| Sync group lifecycle: power-driven → session-driven | #3947 | Invalidates the sync-group half of `06-grouping.md` |
| Role-based API auth → scope-based (`Scope` enum, `required_scope`) | #4613 | `01-event-system.md`, `12-webserver-api.md`, every command table |
| `controllers/config.py` → `controllers/config/` package | #4484 | `02-configuration.md` |
| `controllers/music.py` + `controllers/media/` → `controllers/music/` package | #4266 | `08-media-library.md` |
| `controllers/metadata.py` → `controllers/metadata/` package | #4265, #4838 | `14-metadata.md` |
| `controllers/player_queues.py` → `controllers/player_queues/` package | #4263, #4509 | `09-player-queues.md` |
| Radio mode → dynamic playlists + bounded managed pool | #4498, #4479, #4513 | `09-player-queues.md` |
| Smart fades rebuilt as planner → selection → assembly → renderer | #4532, #4580, #4591 | New `17-smart-fades.md` |
| Audio analysis became a passive observer of `AudioBuffer` | #4442 | `16-audio-analysis.md`, `10-streaming-pipeline.md` |
| `AudioProcessingManager` / bit-perfect fidelity chain | #4793, #5087 | `10-streaming-pipeline.md` |
| Imageproxy moved to opaque image IDs | #3960, #4544 | `14-metadata.md`, `12-webserver-api.md` |
| Three new core controllers: translations, diagnostics, dashboard | #4200, #4652, #4887 | `00-overview.md`, new docs |
| Setup flow engine | #4952, #5010, #5022 | `02-configuration.md`, `15-provider-lifecycle.md` |

## Structural decisions

- **Baseline:** Phase 0 fast-forwards `origin/dev` to `upstream/dev` and merges it into a new
  branch off `docs/architecture`. Every later phase therefore edits docs *in a working tree that
  contains the code being described* — no side worktree needed after Phase 0.
- **Branch and PR shape:** one long-lived branch, `docs/architecture-refresh`, with a single PR
  into `docs/architecture`. Each phase lands **one commit** on that branch and pushes, so the PR
  grows incrementally and can be reviewed as a whole at the end.
- **New doc files (5):** `17-smart-fades.md`, `18-ai-and-mcp.md`, `19-authentication.md`,
  `20-background-tasks.md`, `21-localization.md`. Everything else folds into the existing
  docs as new sections: dashboard casting → `12-webserver-api.md`, diagnostics →
  `20-background-tasks.md`, setup flows → `02-configuration.md`, recommendations and
  recency → `08-media-library.md`.
- **In-tree READMEs:** upstream now ships `README.md` files in most controller and several
  provider directories. Our docs **complement** them — we own cross-cutting flows, invariants,
  and design rationale, and link to in-tree READMEs for module inventories and config keys.
  Where an in-tree README has itself gone stale, we fix it (Phase 1).

## Phases

Build these in order. Each is a separate plan file and produces exactly one commit.

| Phase | Plan file | Scope | Size |
| --- | --- | --- | --- |
| 0 | `arch_docs_v2_phase00_baseline.plan.md` | Sync `origin/dev` to `upstream/dev`, cut `docs/architecture-refresh`, merge, open the PR | S |
| 1 | `arch_docs_v2_phase01_intree_readmes.plan.md` | Fix the 11 stale upstream in-tree `README.md` files (of 20 audited) | M |
| 2 | `arch_docs_v2_phase02_core_framework.plan.md` | `00-overview.md` + core-controller framework + `15-provider-lifecycle.md` | M |
| 3 | `arch_docs_v2_phase03_configuration.plan.md` | `02-configuration.md` rewrite: package split, encryption, migrations, setup flows, queue/DSP config, cache SWR | L |
| 4 | `arch_docs_v2_phase04_player_model_controller.plan.md` | `03-player-model.md`, `04-player-controller.md` | L |
| 5 | `arch_docs_v2_phase05_grouping_volume.plan.md` | `06-grouping.md`, `07-volume.md` — session lifecycle + AudioSource volume | L |
| 6 | `arch_docs_v2_phase06_protocol_linking.plan.md` | `05-protocol-linking.md` — derived transports, migration edge cases | M |
| 7 | `arch_docs_v2_phase07_player_queues.plan.md` | `09-player-queues.md` — package, `PlayerQueueData`, managed pool, autoplay, smart shuffle | L |
| 8 | `arch_docs_v2_phase08_streaming.plan.md` | `10-streaming-pipeline.md` — audio processing, overlay, DSP catalog, AudioSource path | L |
| 9 | `arch_docs_v2_phase09_audio_analysis_smart_fades.plan.md` | `16-audio-analysis.md` + NEW `17-smart-fades.md` | L |
| 10 | `arch_docs_v2_phase10_media_library.plan.md` | `08-media-library.md` — package, search, schema, recommendations, recency | L |
| 11 | `arch_docs_v2_phase11_metadata.plan.md` | `14-metadata.md` — package, opaque imageproxy, priorities, palettes | M |
| 12 | `arch_docs_v2_phase12_plugin_system.plan.md` | `11-plugin-system.md` — the `PluginSource` → `AudioSource` rewrite | L |
| 13 | `arch_docs_v2_phase13_ai_and_mcp.plan.md` | NEW `18-ai-and-mcp.md` + plugin ecosystem sections | M |
| 14 | `arch_docs_v2_phase14_webserver_auth.plan.md` | `12-webserver-api.md` + NEW `19-authentication.md` | L |
| 15 | `arch_docs_v2_phase15_events_discovery.plan.md` | `01-event-system.md`, `13-discovery.md` | M |
| 16 | `arch_docs_v2_phase16_tasks_localization_index.plan.md` | NEW `20-background-tasks.md`, NEW `21-localization.md`, `README.md` catalog, cross-doc sweep | M |

## Conventions for every phase

1. **Pre-flight verification.** Before editing, re-read the relevant code in the working tree
   (post-Phase-0 it is current `upstream/dev`) and confirm each claim the plan makes. Upstream
   moves fast; treat every specific in these plans as a lead to verify, not gospel.
2. **Cite real symbols.** Reference actual file paths, class names, and method names. Prefer
   naming the module over quoting large code blocks.
3. **Complement, don't duplicate.** If an in-tree README already owns a module-inventory table
   or config-key list, link to it instead of restating it.
4. **PR numbers.** Attribute behavior changes to the upstream PR that introduced them, as the
   existing docs already do.
5. **Verify before committing.** Run `pre-commit run --all-files`, then confirm
   `git diff --stat` touches only documentation files.
6. **One commit per phase**, `docs(architecture): ...`, pushed to `docs/architecture-refresh`.

## Sources

The per-phase scope lists were produced by a parallel audit of `upstream/dev` against the
current docs. Each phase plan carries the concrete findings for its area.

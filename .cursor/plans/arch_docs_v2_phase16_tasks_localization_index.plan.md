---
name: arch_docs_v2_phase16_tasks_localization_index
overview: "Phase 16, final. Create 20-background-tasks.md (TasksController plus diagnostics) and 21-localization.md (the strings.json to Lokalise pipeline and runtime resolution), update the docs README catalog and reading paths for all five new files, then run a cross-doc consistency sweep and prepare the PR for review."
todos:
  - id: preflight
    content: "Pre-flight: verify the TasksController surface, diagnostics sections, and translation pipeline against the working tree"
    status: pending
  - id: newdoc_tasks
    content: "Create docs/architecture/20-background-tasks.md covering TasksController, scheduling, API, events, and config"
    status: pending
  - id: newdoc_diagnostics
    content: "20-background-tasks.md: add the diagnostics section (DiagnosticsController, pluggable sections, log capture, sanitization)"
    status: pending
  - id: newdoc_localization
    content: "Create docs/architecture/21-localization.md covering the translation pipeline and runtime resolution"
    status: pending
  - id: readme_catalog
    content: "docs/architecture/README.md: add catalog rows for 17-21, fix the controller count, and update the reading paths"
    status: pending
  - id: sweep_stale
    content: "Cross-doc sweep for stale symbols and paths across the whole docs tree"
    status: pending
  - id: sweep_links
    content: "Verify every internal doc link and every in-tree README link resolves"
    status: pending
  - id: sweep_consistency
    content: "Reconcile facts stated in more than one doc so the phases do not contradict each other"
    status: pending
  - id: pr_ready
    content: "Update the PR description, check all phase boxes, and summarize the refresh for review"
    status: pending
isProject: false
---

# Phase 16 — Background tasks, localization, index, and final sweep

Two new files, the catalog update, and the consistency pass that makes the whole refresh hang
together. Run this last.

## New file: `docs/architecture/20-background-tasks.md`

`controllers/tasks/` is a substantial subsystem with no architecture doc. The in-tree
`controllers/tasks/README.md` is brief and current — link to it and cover what it doesn't.

- **`TasksController`:** the job model, scheduled versus ad-hoc tasks, task IDs, log capture, and
  persistence.
- **API surface:** roughly nine commands (enumerate from the code), with their required scopes.
- **Config:** `tasks` is now in `CONFIGURABLE_CORE_CONTROLLERS` with a `max_concurrent_tasks`
  setting (#4914), and it has an icon like other core modules (#5084). Cross-link Phase 2.
- **Events:** `EventType.TASKS_UPDATED`, and the WebSocket special-casing noted in
  `12-webserver-api.md`.
- **Consumers:** music sync, cache maintenance, metadata maintenance tasks (cross-link Phases 10 and
  11), and the audio analysis background scan (Phase 9).
- **The three "task" concepts.** Be explicit, because the overloading is genuinely confusing:
  `mass.create_task` (fire-and-forget internal work), `helpers/util.TaskManager` (bounded
  parallelism), and `TasksController` (user-visible long-running jobs). Cross-link Phase 15.

### Diagnostics section

`controllers/diagnostics/` plus `helpers/diagnostics.py` (#4652, #4675). Cover the `diagnostics/get`
command and its `Scope.SYSTEM_MANAGE` requirement, the pluggable `get_diagnostics()` hook on core
controllers and providers (cross-link Phase 2), log capture via
`install_diagnostics_log_handler()`, and sanitization/redaction. Note that the HTTP download endpoint
was removed (#4709) so nobody documents a route that isn't there.

Diagnostics shares this file rather than getting its own because both are operational
observability and neither alone justifies a doc.

## New file: `docs/architecture/21-localization.md`

`controllers/translations/` (#4200, #4261, #4299). Cover:

- The pipeline: per-controller and per-provider `strings.json` → `build_translations.py` →
  `music_assistant/translations/en.json` → Lokalise → the other locale files.
- Runtime resolution: the `core.{domain}` and `provider.{domain}` key namespaces, the
  `translation_owner` attribute (cross-link Phase 2), and how translation keys reach config entries
  and error messages (`ProviderError` carries `translation_key` / args / owner — cross-link Phase 2).
- The API: `translations/locales`, and the WebSocket `translations/set_locale` pre-dispatch command
  (cross-link Phase 14).
- Why `TranslationController.setup()` runs first and sequentially during startup (cross-link Phase 2).
- The 38 supported locales, referencing `constants.py:LOCALES` rather than hardcoding the list
  (cross-link Phase 11's locale-count fix).

## `docs/architecture/README.md`

- Add catalog rows for `17-smart-fades.md`, `18-ai-and-mcp.md`, `19-authentication.md`,
  `20-background-tasks.md`, `21-localization.md`.
- The intro says "10 core controllers" — it is 13 instantiated, 9 configurable. Align with the
  wording Phase 2 used in `00-overview.md`.
- Update the Controller Documentation table of in-tree READMEs (several were added upstream; Phase 1
  will have touched some of them).
- Update the recommended reading paths, including a system-operations path through
  `20-background-tasks.md`.

## Cross-doc sweep

Run these across the whole `docs/architecture/` tree and fix or justify every hit. The point is to
catch places where an earlier phase corrected a fact in one doc but left it stale in another.

```bash
rg -n "PluginSource|in_use_by|get_plugin_sources" docs/architecture/
rg -n "required_role" docs/architecture/
rg -n "controllers/config\.py|controllers/metadata\.py|controllers/music\.py|controllers/player_queues\.py|controllers/media/" docs/architecture/
rg -n "radio_mode_base_tracks|_fill_radio_tracks|dont_stop_the_music_enabled" docs/architecture/
rg -n "loudness_measurements|smart_fades_analysis|models/smart_fades" docs/architecture/
rg -n "pluginsource|alimiter|get_player_filter_params" docs/architecture/
rg -n "CONF_MEMBERS_FILTER|supports_dynamic_leader_switching" docs/architecture/
rg -n "10 core controllers|imageproxy\?" docs/architecture/
rg -n "MA-[X0-9]{4}-" docs/architecture/
```

Some hits will be legitimate historical references ("removed in #3659", "was previously
`PluginSource`"). Keep those; the round-1 sweep established that convention. What must not survive is
anything stated in the present tense that is no longer true.

Then verify links:

- Every relative link between architecture docs resolves.
- Every link to an in-tree README points at a file that exists.
- Mermaid diagrams still render — check for stray whitespace inside node definitions, which broke a
  diagram during round 1.

Then reconcile facts asserted in more than one place. Known overlaps to check: the controller
inventory (Phase 2 and this README), scope-based auth (Phases 2, 3, 4, 10, 14, 15), queue-scoped
crossfade and normalization (Phases 3, 7, 8), `group_volume` `exclude_self` (Phases 4 and 5), the
`AudioSource` volume path (Phases 4, 5, 12), analysis hand-off (Phases 8 and 9), and the DB schema
table list (Phases 3 and 10).

## PR readiness

- `pre-commit run --all-files`.
- `git diff --stat docs/architecture-refresh...docs/architecture` — confirm only `docs/` and
  `.cursor/plans/` changed beyond the Phase 0 baseline merge, and that Phase 1's in-tree README
  edits are the only changes under `music_assistant/`.
- Update the PR description: check off all phases, and add a short summary of what changed and how to
  review it (by commit, since the combined diff includes the 1096-commit baseline merge).
- Leave PR #6 (`docs/architecture` → `dev`) alone. Merging this PR down into `docs/architecture` and
  submitting #6 upstream is a separate, explicit step for the user to decide on.

## Commit

```
docs(architecture): background tasks, localization, catalog and cross-doc sweep

Phase 16 of the upstream/dev refresh.
```

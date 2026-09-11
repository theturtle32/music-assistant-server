---
name: arch_docs_v2_phase03_configuration
overview: "Phase 3. Substantially rewrite 02-configuration.md: the config controller is now a 10-module mixin package, encryption uses a dedicated key, settings.json has atomic writes plus a migration framework, there is a setup flow engine, config is now per-queue and per-DSP as well as per-player, and the cache controller gained stale-while-revalidate."
todos:
  - id: preflight
    content: "Pre-flight: verify the config package module map, encryption/migration/atomic-IO behavior, setup flow engine, and cache SWR against the working tree"
    status: pending
  - id: package
    content: "02-configuration.md: replace the monolithic config.py description with the package/mixin layout; link to in-tree docs rather than restating module tables"
    status: pending
  - id: hierarchy
    content: "02-configuration.md: extend the config-type hierarchy with PlayerQueueConfig and setup_data"
    status: pending
  - id: core_entries
    content: "02-configuration.md: fix the core config entry contract (no action/values params, handle_config_action + invoke_action, DEFAULT_CORE_CONFIG_ENTRIES)"
    status: pending
  - id: queue_dsp
    content: "02-configuration.md: add per-queue configuration and DSP configuration sections; correct the player config categories and reusable-entry table"
    status: pending
  - id: encryption_io
    content: "02-configuration.md: rewrite the encryption section for CONF_ENCRYPTION_KEY and legacy migration; document atomic writes, backup rotation, and the migration framework"
    status: pending
  - id: setup_flows
    content: "02-configuration.md: add a setup flow engine section (flows.py, setup_data vs values, onboarding)"
    status: pending
  - id: cache_swr
    content: "02-configuration.md: add stale-while-revalidate to the CacheController section; fix the library DB table list"
    status: pending
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: pending
isProject: false
---

# Phase 3 — Configuration and cache

File: `docs/architecture/02-configuration.md`. Roughly half of it needs rewriting. This is the
largest single-file phase after the plugin rewrite.

## Package split (#4484)

`controllers/config.py` (~2106 lines) is now `controllers/config/`, with a ~309-line
`controller.py` composing mixins. Responsibilities found during the audit — verify, then
summarize rather than reproducing as an exhaustive table:

| Module | Role |
| --- | --- |
| `controller.py` | Base `ConfigController`: JSON I/O, encryption, onboard gate, save/load |
| `constants.py` | `DEFAULT_SAVE_DELAY`, `BASE_KEYS`, `PLAYER_QUEUE_CONFIG_OWNER` |
| `helpers.py` | `_with_translation_owner`, `_provider_status` |
| `core.py` | Core module config CRUD + `invoke_action` |
| `providers.py` | Provider config, `setup_data`, status, provider `invoke_action` |
| `players.py` | Player config + player `invoke_action` |
| `queues.py` | Per-queue config API |
| `dsp.py` | Per-player DSP config and presets |
| `flows.py` | Setup / reconfigure flow engine |
| `migrations.py` | `settings.json` schema migrations |

## Config type hierarchy

The doc names three config types. Add:

- **`PlayerQueueConfig`** — per-queue settings under `CONF_PLAYER_QUEUES`.
- **`setup_data`** on provider configs — credentials and one-time setup values, kept separate
  from ongoing `values` (#5017).

## Core config entry contract

- `get_config_entries()` no longer takes `action` / `values`.
- `ConfigEntryType.ACTION` buttons go through `handle_config_action(action)`, invoked via the
  `config/core/invoke_action` API command (#5035).
- All core configs receive `DEFAULT_CORE_CONFIG_ENTRIES` (`log_level`, `max_concurrent_tasks`).

## Player, queue, and DSP configuration

- The doc lists volume normalization and crossfade under the player `"playback"` category. Both
  moved to **per-queue** config with global defaults on the `player_queues` core module and
  tri-state `global` / `enabled` / `disabled` overrides (#4373, #4537).
- `volume_normalization_target` moved to a **streams** global setting (#4369).
- The reusable-config-entries table therefore misrepresents
  `CONF_ENTRY_VOLUME_NORMALIZATION` and `CONF_ENTRY_VOLUME_NORMALIZATION_TARGET` as generic
  player entries. Correct or remove those rows.
- Add a short DSP configuration section for `dsp.py` (per-player DSP, presets). The filter
  catalog itself belongs to Phase 8 — cross-link rather than duplicate.
- Note `music_assistant/helpers/config_entries.py`: only `create_player_selector()` lives there.
  The `ConfigEntry` / `CoreConfig` model classes remain in `music_assistant_models.config_entries`.
  The doc's Key Files row should not imply the models moved.

## Encryption, file I/O, migrations

- **Encryption (rewrite):** the doc says the Fernet key is the first 32 bytes of `CONF_SERVER_ID`,
  base64-encoded. It is now a dedicated `CONF_ENCRYPTION_KEY` generated and stored in settings,
  with a `CONF_ENCRYPTION_KEY_MIGRATED` flag and a `_migrate_legacy_secrets()` pass that
  re-encrypts values previously protected by the server-ID-derived key (#4557). `setup_data`
  string values are encrypted at rest.
- **File I/O:** beyond the debounced save, document atomic write via `.tmp` + `fsync`, backup
  rotation to `settings.json.backup`, and fallback to the backup when the primary fails to load
  (#4534, which fixed total config loss after a power failure).
- **Migrations:** `migrations.py` runs on load with versioned one-off transforms.

## Setup flow engine

New section. `flows.py` / `SetupFlowMixin` drives interactive provider and player setup and
reconfigure flows (#4952, #5010, #5022). Cover: the `setup_data` vs `values` split, onboarding
(`CONF_ONBOARD_DONE`, `config/onboard_complete`), the `config/providers/setup` and `config/flows/*`
API surface, and `EventType.SETUP_FLOW_UPDATED`. Cross-link `15-provider-lifecycle.md`
(`manifest.has_setup_flow`) and note that Phase 14 documents how the WebSocket layer filters
setup-flow events by scope.

## Config change propagation and API scopes

The doc lists only `save_provider_config` / `save_player_config`. Add `config/core/save`,
`config/player_queues/save`, the `invoke_action` endpoints, and the setup flow APIs. Note that
config API commands now require OAuth-style scopes (#4613) and cross-link the new
`19-authentication.md` (Phase 14) rather than explaining scopes here.

## CacheController

- Add **stale-while-revalidate**: `@use_cache(allow_expired_cache=True)`,
  `set(..., allow_expired_cache=True)`, and cleanup retention via `SWR_FALLBACK_MAX_AGE` (90 days).
  `controllers/cache/README.md` covers this — link to it.
- Fix the library database table list: `loudness_measurements` was dropped (data migrated into
  `audio_analysis`); the `thumbnails` constant exists but no table is created (thumbnails are a
  filesystem cache); and `DB_TABLE_SETTINGS`, `DB_TABLE_EXTERNAL_ID_LOOKUP`,
  `DB_TABLE_AUDIOBOOK_ARTISTS`, and `DB_TABLE_AUDIO_ANALYSIS_FAILURES` are missing.
  `DB_SCHEMA_VERSION` now lives in `controllers/music/constants.py`. Keep this list minimal here
  and let Phase 10 own the schema in `08-media-library.md`.
- Update the Key Files rows to the package paths.

## Verification

- Confirm `CONF_ENCRYPTION_KEY`, `CONF_ENCRYPTION_KEY_MIGRATED`, `SWR_FALLBACK_MAX_AGE`,
  `DEFAULT_CORE_CONFIG_ENTRIES`, `PLAYER_QUEUE_CONFIG_OWNER`, and `CONF_ONBOARD_DONE` all exist.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): rewrite configuration doc for the config package, setup flows and encryption

Phase 3 of the upstream/dev refresh.
```

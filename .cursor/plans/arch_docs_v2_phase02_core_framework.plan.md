---
name: arch_docs_v2_phase02_core_framework
overview: "Phase 2. Refresh 00-overview.md for the 13-controller lineup, the new CoreController contract (per-controller strings.json/icons, config, diagnostics, config actions), and the rewritten startup/shutdown order. Fix the provider loading flow, error model, and manifest discovery in 15-provider-lifecycle.md."
todos:
  - id: preflight
    content: "Pre-flight: verify the controller inventory, init/shutdown order, CoreController surface, and provider load flow against the working tree"
    status: pending
  - id: overview_inventory
    content: "00-overview.md: correct the controller count and Component Map; add translations, diagnostics, dashboard rows; note ConfigController is not a CoreController"
    status: pending
  - id: overview_lifecycle
    content: "00-overview.md: rewrite the startup and shutdown lifecycle sections to match mass.py"
    status: pending
  - id: overview_coremodule
    content: "00-overview.md: add a subsection on core modules as first-class settings entities (icon.svg, icon_dark.svg, strings.json, ProviderType.CORE manifests)"
    status: pending
  - id: lifecycle_manifest
    content: "15-provider-lifecycle.md: fix manifest discovery (has_setup_flow, on-demand icons) and the CORE provider-type description"
    status: pending
  - id: lifecycle_loadflow
    content: "15-provider-lifecycle.md: fix the provider loading flow (config seeding/rehydration, timeouts, load concurrency) and the get_config_entries contract"
    status: pending
  - id: lifecycle_errors
    content: "15-provider-lifecycle.md: replace the last_error string model with structured ProviderError / ProviderStatus; update DEFAULT_PROVIDERS"
    status: pending
  - id: lifecycle_core
    content: "15-provider-lifecycle.md: add a CoreController lifecycle section (config, get_config_value, translation_owner, get_diagnostics, handle_config_action, reload)"
    status: pending
  - id: verify
    content: "pre-commit, confirm the diff touches only docs, commit and push"
    status: pending
isProject: false
---

# Phase 2 — Core controller framework, overview, provider lifecycle

Foundational phase: it establishes the controller inventory and lifecycle that later phases
cross-reference. Do this before `02-configuration.md`.

Files: `docs/architecture/00-overview.md`, `docs/architecture/15-provider-lifecycle.md`.

## `00-overview.md`

### Controller inventory

- The doc says MusicAssistant owns **10** core controllers. There are now **12 `CoreController`
  subclasses plus `ConfigController`**, which is *not* a `CoreController`. Say so explicitly — the
  current text implies uniformity that does not exist.
- Add Component Map rows for `TranslationController` (`translations`),
  `DiagnosticsController` (`diagnostics`), and `DashboardController` (`dashboard`).
- `CONFIGURABLE_CORE_CONTROLLERS` (`music_assistant/constants.py`) now has **9** domains —
  `tasks` was added. `translations`, `diagnostics`, and `dashboard` are core controllers but are
  **not** user-configurable settings modules.
- Update the `mass.py` line count reference (~1077 → current; verify at edit time).

### Core modules as settings entities

New subsection. Every controller directory now ships `icon.svg`, `icon_dark.svg`, and
`strings.json`. Architecturally this means core modules are surfaced in the settings UI like
providers: every `CoreController` builds a `ProviderManifest` in `__init__`, but only domains in
`CONFIGURABLE_CORE_CONTROLLERS` get registered into `_provider_manifests` with icons loaded from
the controller directory. `strings.json` feeds the translation pipeline under `core.{domain}.*`
(Phase 16 documents the pipeline itself; cross-link forward).

### Startup and shutdown lifecycle

Rewrite both. Verify against `mass.py`, but the shape found during the audit was:

1. `config.setup()`, then manifest registration.
2. `_load_core_controllers()` instantiates all core controllers and registers configurable
   manifests plus icons — the doc's separate "register manifests" and "instantiate" steps are now
   one step.
3. `TranslationController.setup()` runs **first and sequentially**, so localized strings exist
   before anything serializes.
4. A parallel `TaskGroup` sets up **9** controllers: cache, tasks, streams, music, metadata,
   players, player_queues, diagnostics, dashboard.
5. `post_setup()` runs for the original **7** only — not translations, diagnostics, or dashboard.
6. `_register_api_commands()` runs **before** `WebserverController.setup()`.
7. `install_diagnostics_log_handler()` runs at the very start of `start()`.

Shutdown: after `players`, close `translations` → `diagnostics` → `dashboard`, then `config` →
`cache`.

Also fix Startup Step 1: the server ID is no longer the encryption key source. Encryption uses a
dedicated `CONF_ENCRYPTION_KEY` (#4557). Keep this to one sentence and cross-link to
`02-configuration.md`, which owns the detail (Phase 3).

## `15-provider-lifecycle.md`

Scope note: this phase edits the core-controller and provider-loading parts. The provider
*discovery* parts are Phase 15.

- **Provider taxonomy:** `ProviderType.CORE` is described as "internal only". Core modules now
  appear in the settings UI with manifests and icons. They still cannot be loaded as runtime
  providers — keep that distinction sharp.
- **Manifest discovery:** still detects icons, but also sets `manifest.has_setup_flow` when a
  `setup_flow.py` exists (#4952, #5061), and icons are held in `_provider_icons` and served on
  demand rather than inlined (#4907).
- **Module contract:** the doc says the module must expose
  `get_config_entries(mass, instance_id, action, values)`. It is now an **instance method on
  `Provider`**, called after the instance exists, with no `action`/`values` parameters. One-time
  credentials come from `setup_flow.py` + `setup_data`, not from options entries. `ACTION`-type
  entries are handled by `handle_config_action(action)` via the `invoke_action` API (#5035).
- **Loading flow:** insert the missing steps — `config.seed_stored_config_values(conf)` before
  load; after `setup()`, `config.rehydrate_provider_config(provider)` and
  `provider.config.validate()` before `handle_async_init()`. Timeouts differ: 30s for load, 300s
  for async init.
- **Load concurrency:** regular providers load under `TaskManager(self, PROVIDER_LOAD_CONCURRENCY=8)`,
  not unbounded background tasks (#5040 fixed a startup hang here).
- **Error handling:** `last_error` is no longer `str(exc)` written through raw `config.set(...)`.
  It is a structured `ProviderError` (error code, message, translation key/args/owner) written via
  `config.update_provider_last_error()`, and the UI derives a `ProviderStatus` from it including
  `AUTH_REQUIRED` (#4242, #4717).
- **`DEFAULT_PROVIDERS`:** the 7-tuple example is stale. It now also includes `wiim`,
  `smart_fades`, and `lastfm_recommendations`, and `smart_fades` can auto-remove itself when the
  host is under-specced. Verify the full tuple in `constants.py`.
- **New section — CoreController lifecycle.** The doc barely covers it. Document the current
  contract: the `config: CoreConfig` attribute, typed `get_config_value()`, `translation_owner`,
  `get_diagnostics()`, `handle_config_action()`, and that `reload()` now assigns `self.config`
  before re-running setup.

## Verification

- Confirm every symbol named above exists: `rg "CONFIGURABLE_CORE_CONTROLLERS|PROVIDER_LOAD_CONCURRENCY|update_provider_last_error|seed_stored_config_values|rehydrate_provider_config"`.
- `pre-commit run --all-files`.
- `git diff --stat` touches only `docs/architecture/`.

## Commit

```
docs(architecture): core controller framework, startup order, provider load flow

Phase 2 of the upstream/dev refresh.
```

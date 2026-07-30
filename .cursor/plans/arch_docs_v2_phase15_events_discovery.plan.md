---
name: arch_docs_v2_phase15_events_discovery
overview: Phase 15. Refresh 01-event-system.md for the expanded EventType set, the 4-tuple subscription record, cheaper sync dispatch, and the scope-based api_command; refresh 13-discovery.md for exact mDNS name matching, dual-stack advertisement, periodic HA re-announce, and the current provider discovery matrix.
todos:
  - id: preflight
    content: "Pre-flight: verify the EventType members, subscribe/dispatch internals, and the discovery matrix against the working tree"
    status: completed
  - id: events_types
    content: "01-event-system.md: rebuild the EventType table with the new members and mark retired ones"
    status: completed
  - id: events_internals
    content: "01-event-system.md: fix the subscription tuple and sync callback dispatch"
    status: completed
  - id: events_api
    content: "01-event-system.md: replace required_role with required_scope in the api_command section and fix the registration scan list"
    status: completed
  - id: events_tasks
    content: "01-event-system.md: document create_task changes and cross-reference TaskManager vs TasksController"
    status: completed
  - id: disc_mdns
    content: "13-discovery.md: fix async_find_mdns_service exact-match semantics"
    status: completed
  - id: disc_advertise
    content: "13-discovery.md: fix server advertisement for multi-address publishing and add periodic HA re-announce"
    status: completed
  - id: disc_matrix
    content: "13-discovery.md: rebuild the provider discovery matrix (mDNS types, UPnP targets, manual IP, other mechanisms)"
    status: completed
  - id: lifecycle_disc
    content: "15-provider-lifecycle.md: fix run_provider_discovery's signature and the post-load discovery sequencing"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 15 — Event system and discovery

Files: `docs/architecture/01-event-system.md` (medium–large), `docs/architecture/13-discovery.md`
(medium), plus a small discovery-only patch to `docs/architecture/15-provider-lifecycle.md` (Phase 2
handled the rest of that file).

Related in-tree READMEs: `music_assistant/controllers/discovery/README.md` and
`controllers/tasks/README.md`. Both were current at audit time — link, don't duplicate.

## `01-event-system.md`

### EventType

The doc lists 23 members in five categories; there are now 29 plus an `UNKNOWN` fallback. Rebuild
the table from `music_assistant_models.enums.EventType` rather than from this list, and add at least:

- **Player:** `PLAYER_SLEEP_TIMER_UPDATED`
- **Provider / setup / tasks:** `PROVIDER_EVENT`, `SETUP_FLOW_UPDATED`, `TASKS_UPDATED`,
  `SYNC_TASKS_UPDATED`
- **Dashboard:** `DASHBOARD_SHOW`, `DASHBOARD_HIDE`, `DASHBOARDS_UPDATED`,
  `DASHBOARD_SESSIONS_UPDATED`

Two care points:

- `AUTH_SESSION` is retired (#5030) and no longer emitted. Treat it like `SHUTDOWN` — an enum
  remnant. Do not silently drop it; readers who see it in the enum need to know why it is dead.
- `SYNC_TASKS_UPDATED` exists in the models package but was **not referenced anywhere in server
  code** at audit time. Verify, then either mark it reserved or omit it — do not imply it is live.
- There is **no** `MEDIA_POSITION_JUMPED` event type. Position jumps go through
  `PlayerController.on_player_position_jumped()` and re-emit `PLAYER_UPDATED`. Don't invent an event
  that doesn't exist (cross-link Phase 4).

Also reorganize the categories: split "Provider/Sync" into provider, tasks, setup, and dashboard.

### Internals

- `EventSubscriptionType` is a **4-tuple**: `(cb_func, event_filter, id_filter, is_coro)`. Coroutine
  detection is precomputed at subscribe time (#4295) so `signal_event` avoids per-dispatch
  reflection.
- Sync callbacks are dispatched with `loop.call_soon(cb_func, event_obj)`, not
  `call_soon_threadsafe` — safe because `signal_event` already enforces the event-loop thread
  (#4631). Explain the invariant, since that is the interesting part.

### `@api_command`

Same correction as Phase 14: `required_scope: Scope | None` → `api_required_scope`, plus
`allow_impersonation` → `api_allow_impersonation`. `APICommandHandler.required_role` becomes
`required_scope`. Keep the treatment brief here and cross-link `19-authentication.md`; Phase 14 owns
the scope model. Also extend the `_register_api_commands` scan list (`translations`,
`streams.audio_analysis`, `diagnostics`, `dashboard`).

### Task creation

`mass.create_task` now supports `eager_start=True` (the default), deduplication via `task_id` /
`abort_existing`, and closes duplicate coroutines (#3929). Add a short cross-reference clarifying the
two different things called "tasks": `helpers/util.TaskManager` is a bounded-parallelism helper and
`mass.create_task` is fire-and-forget internal work, while `TasksController` manages user-visible
long-running jobs (Phase 16).

## `13-discovery.md`

### On-demand mDNS lookup

Round 1 added this section, describing a cache scan that matches when the lowercased name
**contains** both the service type and the name filter. Matching is now **exact** on the device-name
portion after stripping an optional RAOP MAC prefix (`aabbccddeeff@DeviceName`), which is what
prevents cross-matching "Foo" against "ATV Foo" (#4098). The docstring in
`controllers/discovery/controller.py` explains it.

### Server advertisement

`publish_ip` (single address) → **`publish_addresses`** (list), giving dual-stack / multi-address
mDNS registration from `webserver.publish_addresses` (#4646). Coordinate with Phase 8's Network
Architecture edit.

### Home Assistant announcement

Not a one-shot on setup: it re-announces every `HA_ANNOUNCE_INTERVAL` (86400s) to rotate the HA
integration token on long uptimes (#4620), with teardown cancelling `HA_ANNOUNCE_TIMER_ID`. The port
value 8094 is right but should cite the `INGRESS_SERVER_PORT` constant.

### Provider discovery matrix

Rebuild from the manifests and `discover_players()` implementations. The audit found:

**mDNS** (`mdns_discovery` in manifest): `sonos` (`_sonos._tcp.`), `chromecast`
(`_googlecast._tcp.`), `airplay` (**four** types: `_companion-link._tcp.`, `_mediaremotetv._tcp.`,
`_airplay._tcp.`, `_raop._tcp.` — the doc lists only two), `heos` (`_heos-audio._tcp.`), `musiccast`
(`_http._tcp.`), `bluesound` (`_musc._tcp.`, `_musp._tcp.` — the doc omits the types),
`bose_soundtouch` (`_soundtouch._tcp.`), `wiim` (`_linkplay._tcp.`), `yandex_station`
(`_yandexio._tcp.`), `hue_entertainment` (`_hue._tcp.`).

**UPnP** (`upnp_discovery`): `dlna` (`urn:schemas-upnp-org:device:MediaRenderer:1`), `samsung_wam`
(`urn:samsung.com:device:RemoteControlReceiver:1`, missing from the doc entirely, #3334),
`roku_media_assistant` (`roku:ecp` — the doc calls it "Roku" and implies generic MediaRenderer).

**Manual IP** (`CONF_ENTRY_MANUAL_DISCOVERY_IPS`): sonos, sonos_s1, chromecast, sendspin, wiim, mpd,
roku_media_assistant, bose_soundtouch, samsung_wam, fully_kiosk. Note that `bose_soundtouch` uses
both mDNS and manual IPs.

**Other mechanisms** worth a row each: `heos` (mDNS controller plus API enumeration), `chromecast`
(PyChromecast `CastBrowser` on the shared Zeroconf instance with a provider-owned browser thread),
`yandex_station` (mDNS plus the Quasar cloud API, #3605), `amplipi` (setup-flow host config plus API
polling — not a manual-IP entry), `sendspin` (native server protocol plus pairing plus manual IPs, no
`mdns_discovery` in its manifest), `local_audio` (soundcard enumeration via the Sendspin bridge),
`msx_bridge` (on-demand registration when TVs connect; empty `discover_players()`), and the
config-driven virtual players (`sync_group`, `universal_group`, `universal_player`).

`ariacast_receiver` is a plugin with no network discovery and `teddycloud` is a music provider —
neither belongs in the player discovery table.

The `_mdns_waiters` attribute, replay-from-cache, per-provider locks, and the 300s UPnP interval were
all verified as still accurate. Leave them.

## `15-provider-lifecycle.md` (discovery only)

- `run_provider_discovery` takes an instance ID:
  `async def run_provider_discovery(self, instance_id: str)`, resolving the provider internally.
- Post-load sequencing: `create_task(_on_provider_loaded())` is fire-and-forget, but **inside** it
  `await provider.loaded_in_mass()` then `await self.run_provider_discovery(...)` run sequentially,
  including `discover_players()` for a `PlayerProvider`. The doc's phrasing implies less ordering
  than exists.
- `DEFAULT_PROVIDERS` mDNS gating now also covers `wiim` alongside sonos, bluesound, and heos.
- `on_player_enabled` scheduling discovery with a 5s delay was verified as accurate.

## Verification

- `rg "publish_addresses|HA_ANNOUNCE_INTERVAL|HA_ANNOUNCE_TIMER_ID|INGRESS_SERVER_PORT|async_find_mdns_service"`.
- `rg "EventType\." music_assistant/ | sort -u` to find which event types the server actually emits.
- `rg "eager_start|abort_existing"` in `mass.py`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): event types, scope-based commands and the discovery matrix

Phase 15 of the upstream/dev refresh.
```

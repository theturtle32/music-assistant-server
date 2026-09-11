---
name: Fix Architecture Doc Inaccuracies
overview: Address verified inaccuracies and gaps from verification reports v1 and v2 across 12 architecture documents. Covers factual errors, missing information, and minor improvements.
todos:
  - id: p1-factual
    content: "Fix 14 factual errors across 9 files: event table (01), provider reload logic (02), play() label (03), cmd_play routing + diagram + event guards (04), group_volume_muted (07), provider_filter (10), select_source + passive + URL (11), HTTP response (12), setup() + concurrency (00, 15)"
    status: completed
  - id: p2-gaps
    content: "Fill 9 gaps across 6 files: get_active_queue (09), group volume redirect + mute asymmetry (07), FALLBACK_FIXED_GAIN + DSP grouping (10), DB tables + PRAGMAs (02), imageproxy dual mount + get_image_url (14), API registration (12), dependent recovery (15), protocol source_list (11)"
    status: completed
  - id: p3-minor
    content: "Apply 7 minor improvements across 5 files: background task + readiness timing (15), queue recovery + progress triggers + preload (09), UGP can_group_with (06), search genres + URI Qobuz (08), crossfade/throttling (10), callback signatures (11)"
    status: completed
isProject: false
---

# Fix Verified Architecture Documentation Inaccuracies

## Validation Summary

I validated every claim in verification reports v1 and v2 against the actual code. The v2 report filtered out many v1 false positives and added several new findings. Below is the consolidated triage covering both reports, followed by the action plan.

---

## Triage: What Is Real vs Not

### Section 1 — Core Architecture

**1.1 (v1) "Docs reference server.py and controllers/events.py"** — FALSE. Neither path appears in any content doc. Dropped in v2.

**1.1 (v2) "Startup diagram implies DiscoveryController is running after config init"** — FALSE. The diagram node at line 71 explicitly says "DiscoveryController instantiation" — it does not say "running" or "setup". Step 11 clearly shows "DiscoveryController.setup()" separately. The diagram is accurate. **No fix needed.**

**1.2a "@api_command and alias"** — NOT A DOC ERROR. The docs correctly show `alias` on `APICommandHandler`, not on the decorator. v2 suggests a clarification that the decorator itself doesn't accept `alias`. This is already clear from the code snippet shown (which only has `command`, `authenticated`, `required_role`). **No fix needed.**

**1.2b "PlayerQueuesController subscribes to event bus"** — Dropped in v2. Not an issue.

**1.2c "SYNC_TASKS_UPDATED listed but never signaled"** — REAL. [01-event-system.md](docs/architecture/01-event-system.md) line 14 lists `SYNC_TASKS_UPDATED`. This event type doesn't exist in the codebase. Confirmed in both v1 and v2.

**1.2d "WebSocket player_filter only on subset"** — REAL. Confirmed: `_subscribe_to_events` only applies `player_filter` to 7 specific event types (PLAYER_ADDED/REMOVED/UPDATED, QUEUE_ADDED/ITEMS_UPDATED/TIME_UPDATED/UPDATED). The docs should note this is not blanket filtering.

**1.3 / 1.2 (v2) "Missing genre_media_item_exclusion table"** — REAL. Not in `02-configuration.md`'s DB table listing.

**1.2 (v2) "Provider vs Core reload logic"** — REAL (new in v2). [02-configuration.md](docs/architecture/02-configuration.md) line 160 says the default `update_config` in "both `CoreController` and `Provider` checks if any changed entry has `requires_reload=True`". This is wrong for `Provider` — the `Provider.update_config` reloads on *any* non-log-level config change without checking `requires_reload`. Verified in `models/provider.py` lines 66-89.

**1.4a / 1.3 (v2) "Provider class diagram shows setup()"** — REAL. Line 123 in `15-provider-lifecycle.md` shows `+setup()` as an instance method. Confirmed: no such method exists on `Provider`.

**1.4b (v2) "loaded_in_mass() as background task"** — REAL. The flowchart should clarify this is a background task via `create_task()`, not an awaited step.

**1.4c (v2) "Dependent unloads after load_provider"** — REAL gap. The recovery path in `load_provider` (lines 707-712 of mass.py) unloads unavailable dependents. This is undocumented.

### Section 2 — Players, Grouping, Volume

**2.1a "play() claimed as always available"** — REAL. [03-player-model.md](docs/architecture/03-player-model.md) line 208 says `play()` is "*(always available)*". It raises `NotImplementedError` if not implemented.

**2.1b (v1 only) "UniversalPlayer GROUP in config but PLAYER on class"** — FALSE. Dropped in v2.

**2.1c "cmd_play routing table is inverted"** — REAL. [04-player-controller.md](docs/architecture/04-player-controller.md) line 90 says "If paused with queue -> player_queues.resume". The actual code: if NOT paused and queue exists -> `player_queues.resume`; if paused -> falls through to `_handle_cmd_play` (native unpause).

**2.1d "on_stop in command routing diagram"** — REAL. Line 56 shows `plugin.on_stop/on_pause/...`. No `on_stop` callback exists on `PluginSource`.

**2.1e "get_active_queue undocumented"** — REAL gap. The 4-step resolution chain is not explained in any doc.

**2.2a (v2) "UGP can_group_with"** — REAL but minor. Applies to dynamic groups only; static groups return static member list.

**2.3a "cmd_group_volume sync leader redirect"** — REAL gap. `cmd_group_volume` redirects sync followers to the sync leader. Undocumented.

**2.3b "cmd_group_volume_mute no redirect"** — REAL gap. `cmd_group_volume_mute` does NOT redirect to sync leader (asymmetry with `cmd_group_volume`).

**2.3c (v2) "group_volume_muted mixed state"** — REAL. [07-volume.md](docs/architecture/07-volume.md) line 116 says "True only if all powered members are muted. False if at least one is unmuted." The actual code returns `None` when the state is *mixed* (some muted, some unmuted). Lines 904-908 of `models/player.py`: `any_unmuted and not any_muted -> False`; `any_muted and not any_unmuted -> True`; else `None` (the mixed case).

### Section 3 — Media, Queues, Streaming

**3.1a (v2) "Global search doesn't populate genres"** — REAL but minor. `search_library` skips `MediaType.GENRE`.

**3.1b (v2) "URI parsing Qobuz support"** — REAL but minor. `parse_uri` supports any `https://open.*` URL (Spotify AND Qobuz), not just Spotify.

**3.2a "play_index allow_repeat=False on failure"** — REAL gap. Undocumented error recovery behavior.

**3.2b "queue_buffer_completed resume"** — REAL gap. Undocumented resume-after-idle recovery path.

**3.2c "Resume position for podcasts/audiobooks"** — REAL but minor.

**3.3a "provider_filter in get_stream_details"** — REAL (new in v2). [10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md) line 123 calls it "an optional per-player provider_filter". It's actually the *playback user's* `provider_filter`, evaluated in a two-phase loop (preferred providers first, then all others).

**3.3b "Missing FALLBACK_FIXED_GAIN"** — REAL. The normalization modes table is missing this mode.

**3.3c "is_grouping_preventing_dsp"** — REAL gap. DSP disabled in unsupported group setups is undocumented.

**3.3d "Flow throttling with -readrate"** — REAL but minor.

### Section 4 — Plugins, API, Infrastructure

**4.1a "select_source order"** — REAL. The sequence diagram and text show `on_select()` before `in_use_by`. Code does the opposite.

**4.1b "__final_source_list passive filter"** — REAL. Line 112 says "non-passive" but code appends ALL plugin sources.

**4.1c (v2) "Plugin stream URL missing format suffix"** — REAL. [11-plugin-system.md](docs/architecture/11-plugin-system.md) line 197 says `/pluginsource/{source_id}/{player_id}`. Actual route: `/pluginsource/{plugin_source}/{player_id}.{fmt}` (line 301 of streams controller).

**4.1d "Callback signatures async"** — REAL but minor. Tables show `() -> None` but should show `Awaitable[None]`.

**4.2a (v1) "Missing routes"** — FALSE. Dropped in v2.

**4.2b (v2) "HTTP JSON-RPC returns raw JSON, not SuccessResultMessage"** — REAL. [12-webserver-api.md](docs/architecture/12-webserver-api.md) line 211 says HTTP endpoint returns `SuccessResultMessage`. Code at line 585 of `controller.py` returns `web.json_response(result)` — raw result, no envelope. The `SuccessResultMessage` wrapper is WebSocket-only.

**4.2c (v2) "API registration scans fixed list, not all controllers"** — REAL. [12-webserver-api.md](docs/architecture/12-webserver-api.md) line 123 says "scans all controllers". Code at lines 769-778 of `mass.py` scans a fixed tuple of 9 instances: `self`, `config`, `metadata`, `tasks`, `music`, `players`, `player_queues`, `webserver`, `webserver.auth`. Should clarify this is a fixed list and that other commands (party, genres) are registered dynamically via `register_api_command`.

**4.3a "Image proxy dual mount"** — REAL. `14-metadata.md` line 159 only mentions the streams server. It's also on the webserver (line 277 of `webserver/controller.py`).

**4.3b "MetadataProvider NotImplementedError"** — REAL. Verified: raises `NotImplementedError` when feature is declared but method not overridden; returns `None` when feature is not declared.

---

## Action Plan — Edits by File

### Priority 1 — Factual Errors (incorrect statements)

1. **[01-event-system.md](docs/architecture/01-event-system.md)** line 14: Remove `SYNC_TASKS_UPDATED` from the event table (it doesn't exist in the codebase).

2. **[02-configuration.md](docs/architecture/02-configuration.md)** line 160: Fix the claim that both `CoreController` and `Provider` check `requires_reload`. `Provider.update_config` reloads on *any* non-log-level config change without checking `requires_reload`. Rewrite to distinguish the two behaviors.

3. **[03-player-model.md](docs/architecture/03-player-model.md)** line 208: Change `play()` from "*(always available)*" to "*(required — must implement)*".

4. **[04-player-controller.md](docs/architecture/04-player-controller.md)** line 90: Fix `cmd_play` routing table entry. Current: "If paused with queue -> player_queues.resume". Correct: "If not paused and queue exists -> `player_queues.resume` / if paused -> `_handle_cmd_play` (native unpause)".

5. **[04-player-controller.md](docs/architecture/04-player-controller.md)** line 56: Fix Mermaid diagram — change `plugin.on_stop/on_pause/...` to `plugin.on_pause/on_play/...` (no `on_stop` callback exists).

6. **[04-player-controller.md](docs/architecture/04-player-controller.md)** line 239: Fix "three player events (all excluding PROTOCOL players)". Only `PLAYER_UPDATED` excludes PROTOCOL players. `PLAYER_OPTIONS_UPDATED` and `PLAYER_CONFIG_UPDATED` fire for all player types including PROTOCOL.

7. **[07-volume.md](docs/architecture/07-volume.md)** line 116: Fix `group_volume_muted` description. Current: "True only if all muted. False if at least one unmuted." Missing the mixed case: returns `None` when some members are muted AND some are unmuted (not just when no members support mute).

8. **[10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md)** line 123: Fix `provider_filter` description. Current: "optional per-player provider_filter". Correct: the *playback user's* `provider_filter`, evaluated in a two-phase provider walk (preferred providers first, then all others).

9. **[11-plugin-system.md](docs/architecture/11-plugin-system.md)** lines 140-141, 156-157: Fix the `select_source` sequence — `in_use_by` is set BEFORE `on_select()`, not after. Both the Mermaid diagram and the numbered list need reordering.

10. **[11-plugin-system.md](docs/architecture/11-plugin-system.md)** line 112: Change "non-passive plugin sources" to "all plugin sources" (no passive filter in code).

11. **[11-plugin-system.md](docs/architecture/11-plugin-system.md)** line 197: Fix plugin stream URL. Current: `/pluginsource/{source_id}/{player_id}`. Correct: `/pluginsource/{source_id}/{player_id}.{fmt}` (format suffix required).

12. **[12-webserver-api.md](docs/architecture/12-webserver-api.md)** line 211: Fix HTTP JSON-RPC response description. The HTTP endpoint returns raw JSON (`web.json_response(result)`), NOT a `SuccessResultMessage` envelope. The `SuccessResultMessage` wrapper is WebSocket-only.

13. **[15-provider-lifecycle.md](docs/architecture/15-provider-lifecycle.md)** line 123: Remove `+setup()` from the `Provider` class diagram (it's a module-level function, not an instance method).

14. **[00-overview.md](docs/architecture/00-overview.md)** line 95 and **[15-provider-lifecycle.md](docs/architecture/15-provider-lifecycle.md)** line 244: Fix provider-load concurrency claim. The docs say `TaskManager(self, 2)` enforces a concurrency limit of 2, but `_load_providers()` calls `tg.create_task()` which does NOT use the semaphore. Only `create_task_with_limit()` honors the semaphore. The actual behavior is unlimited concurrency. Either note this as a known discrepancy (the TaskManager is passed limit=2 but it's not enforced on this code path) or simply describe it as "loaded concurrently as background tasks".

### Priority 2 — Missing Information (gaps)

15. **[09-player-queues.md](docs/architecture/09-player-queues.md)**: Add a section documenting `get_active_queue` — the 4-step resolution chain (sync leader -> active GROUP -> active_source/player_id -> protocol parent). This is a cross-cutting concept missing from all docs.

16. **[07-volume.md](docs/architecture/07-volume.md)**: Add documentation of `cmd_group_volume` sync leader redirect (controller lines 692-695). Also note the asymmetry: `cmd_group_volume_mute` does NOT redirect to sync leader — calling it on a sync follower is a no-op.

17. **[10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md)**: Add `FALLBACK_FIXED_GAIN` to the normalization modes table. Description: "Falls back to `FIXED_GAIN` when no loudness measurement is available".

18. **[10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md)**: Add a note about `is_grouping_preventing_dsp` (`helpers/audio.py`) — DSP is disabled (`DSPState.DISABLED_BY_UNSUPPORTED_GROUP`) for grouped players when `MULTI_DEVICE_DSP` is not a supported feature.

19. **[02-configuration.md](docs/architecture/02-configuration.md)**: Add `genre_media_item_exclusion` to the DB table listing. Also add missing PRAGMAs `analysis_limit=10000` and `journal_size_limit=6144000` to the PRAGMA table, plus `PRAGMA optimize` at close time.

20. **[12-webserver-api.md](docs/architecture/12-webserver-api.md)** line 123: Clarify that `_register_api_commands` scans a fixed list of 9 class instances (`self`, `config`, `metadata`, `tasks`, `music`, `players`, `player_queues`, `webserver`, `webserver.auth`), not "all controllers". Note that additional commands (party, genres) are registered dynamically at runtime via `register_api_command`.

21. **[14-metadata.md](docs/architecture/14-metadata.md)** line 159: Note that `/imageproxy` is mounted on BOTH the streams server (8097) and the main webserver (8095). Add context: `get_image_url()` chooses the base URL based on `prefer_stream_server` parameter — webserver by default, streams server when `prefer_stream_server=True`.

22. **[15-provider-lifecycle.md](docs/architecture/15-provider-lifecycle.md)**: Add the dependent recovery mechanism — after a successful `load_provider`, the server unloads any loaded-but-unavailable providers whose `depends_on` matches the just-loaded domain (mass.py lines 707-712), triggering them to retry.

23. **[11-plugin-system.md](docs/architecture/11-plugin-system.md)**: Add note that PROTOCOL players return early from `__final_source_list` (line 1724 of player.py) and therefore never show plugin sources in their visible source list. Plugin audio can still be routed through control logic, but the source list omission means protocol players won't offer plugin sources in their UI.

### Priority 3 — Minor Improvements (nice to have)

24. **[15-provider-lifecycle.md](docs/architecture/15-provider-lifecycle.md)**: Clarify that `loaded_in_mass()` + `run_provider_discovery()` run as a background task via `create_task()` (not awaited in the `_load_provider` sequence). Note that `PROVIDERS_UPDATED` is signaled and controller hooks run BEFORE these background tasks complete.

25. **[09-player-queues.md](docs/architecture/09-player-queues.md)**: Add notes about: error recovery with `allow_repeat=False`, `queue_buffer_completed` resume-after-idle path, resume position for podcasts/audiobooks, and `_preload_streamdetails` waiting up to 120s for the buffered item to become `queue.current_item`.

26. **[09-player-queues.md](docs/architecture/09-player-queues.md)** line 295: Fix progress reporting description. Current: "Every 30 seconds". Actual: triggers on state changes, `current_item_id` changes, OR the 30-second cadence — not purely time-based.

27. **[06-grouping.md](docs/architecture/06-grouping.md)**: Clarify that UGP `can_group_with` returning all provider instance_ids only applies to dynamic groups.

28. **[08-media-library.md](docs/architecture/08-media-library.md)**: Note that `search_library` does not populate `MediaType.GENRE`. Update URI table to note Qobuz alongside Spotify for `https://open.*` URLs.

29. **[10-streaming-pipeline.md](docs/architecture/10-streaming-pipeline.md)**: Add notes about crossfade sample-rate constraint (`CONF_ENTRY_CROSSFADE_DIFFERENT_SAMPLE_RATES`) and flow stream `-readrate` throttling.

30. **[11-plugin-system.md](docs/architecture/11-plugin-system.md)**: Fix callback signature types in the table from `() -> None` to `Awaitable[None]`.

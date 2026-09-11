# Independent Verification — Cursor Grok 4.5

**Commit under review:** `a61247ff4` (detached worktree `/tmp/ma-arch-review`)
**Corpus:** `docs/architecture/00-overview.md` … `21-localization.md` + `README.md` (23 files)
**Ground truth:** `music_assistant/` in the worktree; `music_assistant_models` from the pinned venv when model definitions mattered
**Method:** Isolated worktree with `docs/architecture/plans/` and `.cursor/` removed before any reading. Six parallel domain agents plus independent parent spot-checks of every Critical/Major claim against source. Prior verification reports were not consulted.

---

## Domain: Core, events, configuration, provider lifecycle, discovery

### Verified Accuracies

- **Controller map and startup/shutdown order.** Thirteen controllers (config + twelve `CoreController`s); config is not a `CoreController` (`mass.py` `222–223`, `controllers/config/controller.py` `62`: `self.initialized = False`). `CONFIGURABLE_CORE_CONTROLLERS` is exactly the nine listed domains (`constants.py` `305–315`). Startup sequence in `MusicAssistant.start()` matches the overview flowchart through diagnostics install → config → discovery instantiate → manifests → storage → `_load_core_controllers` → translations alone → parallel setup of nine → post_setup of seven → API registration → webserver → discovery setup → builtins → regular (`mass.py` `215–289`). Shutdown order matches (`mass.py` `305–318`).
- **Event bus.** `EventType` has 30 members including `UNKNOWN`. `signal_event` suppresses when `closing`, enforces the loop thread, snapshots subscribers, dispatches async via `create_task` and sync via `call_soon` (`mass.py` `580–609`). `SHUTDOWN` still has a dangling subscriber in `helpers/aiohttp_client.py` `220` and is never signaled.
- **Config persistence.** Debounced save (`DEFAULT_SAVE_DELAY = 5`), atomic write via `.tmp` + `fsync` + parseable-backup rotate + rename (`controllers/config/controller.py` `287–307`).
- **Discovery intervals.** UPnP every 300s, HA re-announce every 86400s, `_mass._tcp.local.` advertisement (`controllers/discovery/controller.py` `45–51`, `253`).

### Inaccuracies and Stale Info

1. **Severity: Critical | Kind: Wrong | Confidence: High**
   **Builtin provider load failure is documented as fatal; the code never aborts startup on it.**
   Docs (`00-overview.md` mermaid step 13 / prose; `15-provider-lifecycle.md` `builtin` comment and failure-impact table) claim TaskGroup await means “if any fails, startup aborts” / “Fatal — server startup aborts”.
   Actual path:

```1088:1090:music_assistant/mass.py
        async with asyncio.TaskGroup() as tg:
            for conf in builtin_configs:
                tg.create_task(self.load_provider(conf.instance_id, allow_retry=True))
```

```885:910:music_assistant/mass.py
        except Exception as exc:
            ...
            will_retry = allow_retry and isinstance(exc, MusicAssistantError)
            if will_retry:
                self.call_later(120, self.load_provider, instance_id, allow_retry, task_id=task_id)
            ...
            return
```

   `load_provider` swallows the exception, so `TaskGroup` completes successfully. The same table’s “Auto-retry | Yes” row is consistent with the code and contradicts the “Fatal” row.

2. **Severity: Major | Kind: Wrong | Confidence: High**
   **`API_SCHEMA_VERSION` / `MIN_SCHEMA_VERSION` are attributed to the models package.**
   `00-overview.md` Multi-Repo table: models repo “Defines `API_SCHEMA_VERSION` / `MIN_SCHEMA_VERSION`”.
   They live on the server:

```48:58:music_assistant/constants.py
API_SCHEMA_VERSION: Final[int] = 41
...
MIN_SCHEMA_VERSION: Final[int] = 28
```

   No such symbols in `music_assistant_models/`. `get_server_info()` fills them from server constants (`mass.py` `371–372`).

3. **Severity: Major | Kind: Wrong | Confidence: High**
   **`13-discovery.md` names wrong virtual-player id prefixes.**
   Doc: ``SGP_``, ``UGP_``, “the universal-player prefix”.
   Actual: `SGP_PREFIX = "syncgroup_"`, `UGP_PREFIX = "ugp_"`, `UNIVERSAL_PLAYER_PREFIX = "up"` (`providers/sync_group/constants.py` `10`; `universal_group/constants.py` `13`; `universal_player/constants.py` `7`). Constant *names* are `SGP_`/`UGP_`; the on-wire prefixes are not.

4. **Severity: Major | Kind: Wrong | Confidence: High**
   **mDNS live-dispatch sequence diagram shows lock-then-resolve; code resolves then locks.**
   Live path (`controllers/discovery/controller.py` `286–294`): `async_request` runs, then `async with lock:` around the provider callback. Prose about serializing callbacks is closer to truth; the diagram is not. Replay holds the lock across resolve+callback.

5. **Severity: Major | Kind: Wrong | Confidence: High**
   **Dependency section claims unloading unavailable dependents “triggers them to retry loading”.**
   After successful `load_provider`, code only unloads (`mass.py` `912–917`). It does not schedule a reload. Dependent (re)load is the earlier config loop in `load_provider_config` (`826–835`).

6. **Severity: Minor | Kind: Stale | Confidence: Medium**
   Atomic settings save cited as PR #4534; the fsync comment in code cites `#5716` (`controllers/config/controller.py` `294`).

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   **`depends_on` with a loaded-but-unavailable dependency is a silent no-op with no retry timer.**
   Gate uses `get_provider(...)` default `return_unavailable=False` (`mass.py` `1189–1192`) and returns without scheduling the 120s `allow_retry` path. Recovery only happens when something successfully loads the dependency and the dependent walk runs. Not documented.

2. **Severity: Minor | Kind: Missing | Confidence: High**
   Live mDNS: `async_request` can overlap across events for one provider; only the callback is serialized. Docs emphasize lock safety without that nuance.

3. **Severity: Minor | Kind: Missing | Confidence: Medium**
   Config debounced save uses `loop.call_later` directly, not `mass.call_later`, so it is outside `_tracked_timers` (`controllers/config/controller.py` `180–192`).

---

## Domain: Player model, player controller, protocol linking, grouping, volume

### Verified Accuracies

- Line counts match: `player.py` 3051, `controller.py` 4215, `protocol_linking.py` 2439.
- `PlayerController(ProtocolLinkingMixin, CoreController)` (`controller.py` `150`). Identifier hierarchy, 15s/45s delayed evaluation, same-domain exclusion at call sites (`protocol_linking.py` `413–441`, `539–541`).
- Sync/universal group session lifecycle: `is_active_session`, `IDLE_GRACE_SECONDS = 10`, `REFORM_DEBOUNCE_SECONDS = 2`, `EXTRA_FEATURES_FROM_MEMBERS` (`providers/sync_group/constants.py` `16–40`).
- Volume: mute lock, device-range scaling, group interpolation with snapshot (`controller.py` `2031–2073`, `3807+`).
- Registration skips fake-power restore for GROUP players; temporary unregister emits `PLAYER_UPDATED` with `available=False`.

### Inaccuracies and Stale Info

1. **Severity: Major | Kind: Wrong | Confidence: High**
   **`03-player-model.md` Protocol Feature Routing claims `power_control` uses `_get_protocol_player_for_feature(..., require_active=True)`.**
   Doc (`03` ~414): “The `power_control`, `volume_control`, and `mute_control` cached properties use this method… Power uses `require_active=True`.”
   `power_control` never calls that helper — only NATIVE/FAKE/NONE/external `PlayerControl` (`models/player.py` `1313–1330`). Volume/mute do call it with `require_active=False`. Same document’s `power_control` Degradation section correctly says power is not delegated to protocol players — internal contradiction.

2. **Severity: Major | Kind: Stale | Confidence: High**
   **`__final_power_state` resolution table still lists “delegate player”.**
   Table (`03` ~232): `FAKE → NATIVE → NONE → delegate player → delegate PlayerControl`. After #3659, `power_control` never returns a player ID; `_handle_cmd_power` has no protocol-player branch (`controller.py` `3722–3753`).

3. **Severity: Major | Kind: Wrong | Confidence: High**
   **`06-grouping.md` State Delegation lead-in inverts raw vs `.state` for playback.**
   Opening claim: reads leader’s *raw* `playback_state` / `elapsed_time`, **not** `leader.state.*`. Code and the later clarification do the opposite:

```964:968:music_assistant/providers/sync_group/player.py
        prev_state = self._attr_playback_state
        new_state = sync_leader.state.playback_state
        self._attr_playback_state = new_state
        self._attr_elapsed_time = sync_leader.state.elapsed_time
        self._attr_elapsed_time_last_updated = sync_leader.state.elapsed_time_last_updated
```

   Raw is required for `current_media` / `active_source` / `source_list`. The section’s table is correct; the emphatic lead sentence is not.

4. **Severity: Minor | Kind: Wrong | Confidence: Medium**
   `__final_volume_level` “every non-FAKE branch” scaling: `NONE` returns `None` before any `scale_volume_from_device()` call.

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   **Inverted parent preference between `__final_current_media` and `__final_active_source`.**
   Media prefers `active_group or synced_to` (`player.py` `2506`); source prefers `synced_to or active_group` (`2847`). Docs list both orders but never explain why they differ or how that prevents sync-group circularity when both are set.

2. **Severity: Minor | Kind: Missing | Confidence: High**
   `set_group_volume` / `cmd_group_volume_mute` use bare `asyncio.gather` (no `return_exceptions=True`) — one child failure raises while siblings may still complete.

3. **Severity: Minor | Kind: Missing | Confidence: Medium**
   Provider reload mid-window: temporary unregister removes the live player while linked parents still hold protocol IDs until re-register + re-evaluation. Pieces are in 04/05; the mid-reload control-routing hole is not.

---

## Domain: Media library, player queues, metadata

### Verified Accuracies

- Eight media sub-controllers with the documented class names (`PlaylistController`, `GenreController`, etc.) under `controllers/music/media/`. Schema `DB_SCHEMA_VERSION = 55`; search soft/hard timeouts 8s/120s (`music/constants.py` `12–35`).
- Match-and-store with `deferred_commit` + `_db_add_lock`; cloned multi-instance mappings use `in_library=None` (`media/base.py` `245–266`; `music/controller.py` `2021–2032`). `SUPPRESS_MEDIA_ITEM_UPDATES` ContextVar (`media/base.py` `92–93`).
- Nightly DB cleanup at 05:00 local; provider-mapping correction every 30 days at 04:00 local (`music/controller.py` `2536–2554`).
- Queue package structure: `PlayerQueuesController(QueueLoaderMixin, PlaybackTrackerMixin, StreamFeederMixin)` over `_PlayerQueuesBase` — matches `09`. Managed pool sizes 25/50/250; `get_active_queue` four-step chain (sync leader → active group → active_source → protocol parent).
- Metadata controller mixin composition matches (`ImageProxyMixin, RadioArtworkMixin, MetadataEnrichmentMixin, CoreController`). Library-only `update_metadata`; refresh interval 90 days. Documented priorities 10/20/25/30/50/90 match those providers (`fanarttv`/`theaudiodb`/`wikipedia`/`itunes_artwork`/base default/`playlist_metadata`) — but see Cover Art Archive omission below.

### Inaccuracies and Stale Info

1. **Severity: Major | Kind: Missing | Confidence: High**
   **Cover Art Archive omitted from `14-metadata.md`.** Builtin stable metadata provider at **priority 40** (`ALBUM_METADATA`, MB release-group lookup) is absent from the enrichment mermaid, priority table, capabilities matrix, and Key Files — so the documented ordering jumps 30 → 50 and understates album-art competition after iTunes.

```47:50:music_assistant/providers/coverartarchive/__init__.py
    def priority(self) -> int:
        """Priority for this provider (lower = more preferred)."""
        return 40
```

2. **Severity: Minor | Kind: Broken | Confidence: High**
   **`14-metadata.md` points at `08-media-library.md#migrations` for LRC normalization, but 08’s Migrations section never mentions it.** The schema ≤53 lyric-normalization migration exists only in code (`controllers/music/migrations.py` `859–861`).

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   Same Cover Art Archive gap affects **radio artwork**: `_get_release_group_artwork` walks providers by priority, so CAA runs after Fanart/TheAudioDB/iTunes. Doc 14 §Radio Lookup Pipeline step 6 names only Fanart/TheAudioDB/iTunes (`controllers/metadata/radio.py` `455–478`).

2. **Severity: Minor | Kind: Missing | Confidence: Medium**
   `09` covers `get_active_queue` well; the seam with sync-group session dissolve (queue survives on the group player while members are released) is split across 06/09 without a single end-to-end “who owns the queue after stop()” narrative.

3. **Severity: Minor | Kind: Missing | Confidence: Medium**
   Queue enrichment resolves via `get_library_item_by_prov_id` (no metadata refresh schedule), while UI `get()` schedules refresh — easy to confuse “library item on the wire” with “provider item_id” (`queue_loader.py` `300–307`; `media/base.py` `547–549`).

4. **Severity: Minor | Kind: Missing | Confidence: Medium** (plugin/stream adjacent)
   `_load_item` still calls `get_stream_details` for `AUDIO_SOURCE` but skips AudioBuffer drive — preload semantics differ for live sources vs tracks.

---

## Domain: Streaming pipeline, audio analysis, smart fades

### Verified Accuracies

- Dedicated streams HTTP port default 8097 (`controllers/streams/constants.py` `DEFAULT_PORT`). No auth; session id validation.
- Collaborating classes: `StreamsController`, `StreamsAudio`, `AudioProcessingManager`, `AudioAnalysisController` — all present. `SmartFadesMixer` under `controllers/streams/smart_fades/`; analysis half in `providers/smart_fades/` with `analysis_version = 3`.
- `AudioSource` realtime bypass (skip buffer/normalization/crossfade) and lifecycle hooks on GET (not HEAD) match `controller.py` / `audio.py`.
- Analysis: `REALTIME_ANALYSIS_MAX_SESSIONS = 2`, `ANALYSIS_MIN_COMPLETENESS_RATIO = 0.9`, `CHUNK_HANG_GUARD_SECONDS = 120.0`, nightly scan at local midnight with 4h budget (`audio_analysis.py` `54–73`, `242–244`).
- FFmpeg major version gate is `MINIMAL_FFMPEG_VERSION = 6` (`helpers/ffmpeg.py` `30`, `719–724`).

### Inaccuracies and Stale Info

1. **Severity: Major | Kind: Wrong | Confidence: High**
   **DSP catalog overstates what the streaming path actually renders.**
   Doc 10 lists `CONVOLUTION`, `SAFETY_LIMITER`, `COMPRESSOR`, `STEREO_WIDTH`, `CROSSFEED` and describes `ComplexFilter`/`afir` as the convolution path.
   `filter_to_ffmpeg_params()` only handles ParametricEQ / ToneControl / Gain / Balance / Transpose / HighLowPass and returns `list[str]` (`helpers/dsp.py` `45–55+`). `ComplexFilter` exists as a type and ffmpeg accepts it, but no production call constructs a `ComplexFilter(` instance. Models without renderers silently contribute nothing.

2. **Severity: Minor | Kind: Wrong | Confidence: High**
   Chromecast flow readrate: doc says `-readrate 1` and `-readrate_initial_burst 6`; code uses `1.1` and `5` (`streams/controller.py` `1024`).

3. **Severity: Minor | Kind: Wrong | Confidence: High**
   Doc 16 Ownership says `setup()` “configures CPU caps”; `setup()` only registers the nightly scan. Caps live in `ensure_inference_runtime_configured()` (later prose in the same doc is correct).

4. **Severity: Minor | Kind: Missing | Confidence: High**
   `get_media_stream` source table omits `StreamType.SHOUTCAST` (`audio.py` `464–467`).

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   **Flow mid-queue restart is undocumented.** `_flow_stream_needs_restart()` exits the flow on `RADIO`/`AUDIO_SOURCE`, or on sample-rate mismatch (`bit_perfect`: any mismatch; `smart`: next rate higher than current) (`audio.py` `3214–3244`). This is the seam between streaming, mixed plugin/radio queues, UGP fan-out, and gapless/crossfade continuity — absent from docs 10/16/17 despite coverage of `select_flow_pcm_format`.

2. **Severity: Minor | Kind: Missing | Confidence: High**
   DSP models without renderers silently no-op while remaining UI-configurable — not stated beside the filter catalog.

---

## Domain: Plugin system, AI and MCP

### Verified Accuracies

- 20 production plugins + `_demo_plugin_provider`. `PluginSource` gone from `music_assistant/`. `AudioSource` fields and defaults match the models package.
- `PluginProvider` hooks (`get_audio_sources`, `on_source_control`, `on_source_selected`/`unselected`, `ai_query`, `get_tts_message`) match `models/plugin.py`.
- Browse filters `can_initiate`; lifecycle: HEAD skips hooks, GET claims before stream.
- AI: no central controller; consumer-specific discovery/timeout/retry policies match the comparison table in spirit; Music Quiz grounding/validation pattern matches.
- `hass` is the in-tree `AI_QUERY`/`TTS` backend.

### Inaccuracies and Stale Info

1. **Severity: Major | Kind: Wrong | Confidence: High**
   **Doc 11: Music Quiz is “the largest plugin … roughly 7,400 lines.”**
   `music_quiz` ≈ 7,415 LOC; `fastmcp_server` ≈ 10,307 LOC / 46 modules. Quiz is not largest by lines.

2. **Severity: Major | Kind: Stale | Confidence: High**
   **Doc 18: FastMCP “roughly 7,500 lines.”** Module-count claim holds; line count is ~10.3k.

3. **Severity: Minor | Kind: Wrong | Confidence: High**
   Doc 11: `get_stream()` “repeats both decisions” (WAV force + flow suppress). Flow is suppressed for `AUDIO_SOURCE`; WAV force is HTTP-path only (`resolve_stream_url`), not `get_stream`.

4. **Severity: Minor | Kind: Wrong | Confidence: Medium**
   Doc 18 consumer table: Smart Playlists discovery = “registry order.” Code uses `get_providers_supporting_feature` (type tiers + priority sort) then `isinstance(PluginProvider)`.

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   **`allow_external_trigger` and `exclusive` are never read by core controllers.** Docs present them as peer routing/capability gates alongside `can_initiate` (which *is* enforced in browse). External start and exclusivity are provider conventions, not controller branches. Comments in streams mention “exclusive ownership” as a lifecycle concept, but the `AudioSource.exclusive` field is not consulted.

2. **Severity: Minor | Kind: Missing | Confidence: High**
   `MediaType.PLUGIN_SOURCE` still exists as a deprecated alias; FastMCP still accepts it. Docs say the old model is gone without noting wire/compat remnants.

---

## Domain: Webserver API, authentication, background tasks, localization

### Verified Accuracies

- Ports 8095 / ingress 8094 / streams 8097. Route map for `/ws`, `POST /api`, auth, sendspin matches `controllers/webserver/controller.py`.
- Scope model: 21 members; `ROLE_SCOPES` / `has_scope` match (`auth_middleware.py` `27–56`, `188–196`). `AuthenticationManager` ~2016 lines.
- Tasks: three-way “tasks” distinction; `MAX_FINISHED_TASK_HISTORY = 100`; package ~1447 lines.
- Localization: 10 controller + 113 provider `strings.json`; ~2476 `en.json` keys; translations setup before other controllers serialize (`mass.py` `249–252`).
- README catalog lists all 23 architecture docs; 593 relative links among them resolve (0 broken, excluding `plans/`).

### Inaccuracies and Stale Info

1. **Severity: Critical | Kind: Wrong | Confidence: High**
   **`auth_middleware` is documented as the live HTTP auth path but is never registered.**
   Doc (`12-webserver-api.md` `326–328`): “Other HTTP routes” use `auth_middleware`; handlers call `require_authentication()`.
   `Webserver.setup` builds `web.Application(...)` with **no middlewares** (`helpers/webserver.py` `72–79`). `auth_middleware` / `require_authentication` are defined (`auth_middleware.py` `173–185`, `371+`) but never attached to the app. Real HTTP auth is per-handler (`_authenticate_api_command` → `get_authenticated_user`). Even the documented allowlist would match every path via `"/"` + `startswith` if the middleware were wired.

2. **Severity: Major | Kind: Wrong | Confidence: High**
   **`music/providers` is not an API command.**
   Doc (`19-authentication.md` ~171) lists ``music/providers``. Only `@api_command("providers", ...)` exists (`mass.py` `433`).

3. **Severity: Minor | Kind: Wrong | Confidence: High**
   “Both filters bypassed for `Scope.ALL`” is overstated. True for `mass.get_providers` and some player list APIs; false for `_apply_user_provider_filter`, `_ensure_provider_filter`, and WS `player_filter` gating, which honor a non-empty filter even for an admin.

4. **Severity: Minor | Kind: Stale | Confidence: Medium**
   Key Files still present `auth_middleware` as an active request-path component (the module *is* live for scopes/context vars/ingress helpers; the middleware *function* is not).

### Missing Cross-Cutting Context

1. **Severity: Major | Kind: Missing | Confidence: High**
   Docs never state that non-`/api` HTTP identity is entirely handler-local, or that the middleware + `require_authentication` helpers are unused dead surface.

2. **Severity: Minor | Kind: Missing | Confidence: Medium**
   Decorator scope checks use the authenticated user before impersonation is applied; impersonated identity is for the handler body via `get_current_user()`.

3. **Severity: Minor | Kind: Missing | Confidence: Medium**
   `tasks/list` requires `SYSTEM_READ`, but visibility of scheduled system tasks (`user_id is None`) still needs `SYSTEM_MANAGE` — a normal `USER` never sees them.

---

## Cross-Document Coherence

### Contradictions between documents

1. **Builtin load fatality (Critical).** `00-overview.md` and `15-provider-lifecycle.md` both assert fatal builtin failure; neither matches `load_provider`’s catch-and-retry behavior. They agree with each other and disagree with the code.
2. **Virtual player prefixes.** `06-grouping.md` correctly documents `syncgroup_` / `ugp_`. `13-discovery.md` incorrectly says `SGP_` / `UGP_`. Readers who trust discovery alone will search for the wrong IDs.
3. **Power control routing.** `03` §power_control Degradation correctly says no protocol delegation; §Protocol Feature Routing incorrectly says `power_control` uses `_get_protocol_player_for_feature`. `04` / #3659 notes align with the Degradation section.
4. **Sync-group state source.** `06` lead paragraph vs its own table vs `sync_group/player.py` — table and code agree (`.state.*` for playback/elapsed); lead paragraph does not.
5. **Auth middleware.** `12` and `19` share the live-middleware story; neither notes it is unwired.
6. **Provider-filter bypass language.** `19` says `Scope.ALL` bypasses both filters; `08` says “non-admin.” Neither documents that browse/library helpers lack the `Scope.ALL` short-circuit that `get_providers` has.
7. **LRC migration cross-reference.** `14` links to `08#migrations` for stored-lyric normalization; `08` never documents that migration (code-only at schema ≤53).

### Terminology inconsistency

- **“Tasks”** — well called out in `20`; still easy to confuse with `mass.create_task` / `TaskManager` when reading `00`/`01`/`15` in isolation.
- **“SGP” / sync group** — constant name `SGP_PREFIX` vs id prefix `syncgroup_` vs player type `GROUP`.
- **`auth_middleware` module vs middleware function** — module is essential; function is dead. Docs blur the two.

### Referential integrity

- All relative links among the 23 architecture docs resolve (plans/ ignored by design).
- README catalog matches the on-disk set (`00`–`21` + `README.md`).
- Linked controller/provider READMEs and root docs referenced from README all exist.
- Historical mentions of deleted `music_assistant/models/smart_fades.py` and `helpers/auth.py` are intentional “was deleted” notes, not live Key Files claims.
- One cross-link to `player_queues/README.md#configuration` resolves (`## Configuration` exists).
- `14` → `08#migrations` resolves as an anchor, but the target section does not cover the claimed LRC content (see finding above).

### Overall assessment

The corpus is generally strong: complex mechanisms (session-driven grouping, protocol linking, AudioSource lifecycle, analysis passive-observer design, scope model, localization pipeline, queue package split) track the code closely, including many edge cases. The Critical gaps are concentrated in **startup failure semantics for builtins** and **HTTP authentication plumbing** — both places where a reader following the docs would implement or debug the wrong control flow. Next-priority fixes are the power-control / sync-group state contradictions inside the player docs, the discovery id-prefix typo, the DSP “catalog vs renderer” gap, the undocumented flow-stream restart seam with live/plugin sources, and Cover Art Archive’s absence from the metadata provider ordering.

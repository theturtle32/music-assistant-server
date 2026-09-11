# Cross-document integration pass — worklist

Stage 1 output. Produced after a single full read of:

- `docs/architecture/*.md` (23 files)
- `music_assistant/controllers/*/README.md` (9 files)
- `music_assistant/providers/*/README.md` + `spotify_connect/ARCHITECTURE.md` (11 files)

plus targeted source verification of every numeric/structural claim listed under
"Verified correct" below. Ground truth is `music_assistant/` at working-tree HEAD
(`0db8cc633`).

Each item is `[ ]` open or `[x]` resolved. An item names the file, the line at time of
writing, what is wrong, what it should say, and the source that settles it.

---

## A. Correctness against the code

### A1. `[x]` `12-webserver-api.md:389` — STUN server list is wrong

**Says:** "three public STUN servers by default — `stun.l.google.com:19302`,
`stun.cloudflare.com:3478`, and `stun.home-assistant.io:3478`."

**Source:** `controllers/webserver/remote_access/gateway.py:79-84` defines
`WebRTCGateway.DEFAULT_ICE_SERVERS` with **four** entries — `stun.home-assistant.io:3478`,
`stun.l.google.com:19302`, `stun1.l.google.com:19302`, `stun.cloudflare.com:3478` — and
`gateway.py:125` uses it whenever the `ice_servers` argument is falsy.
`remote_access/__init__.py:205-225` passes `ice_servers` straight from
`_get_ha_cloud_status()`, which yields nothing when HA Cloud is unavailable. So **basic mode
uses the gateway's four.**

The three-entry list in `remote_access/__init__.py:112-115` is the fallback inside
`RemoteAccessManager.get_ice_servers()`, which is only wired in as
`ice_servers_callback` **when HA Cloud is available** (`__init__.py:228`) — in which case it
returns the HA Cloud set, not the fallback.

**Fix:** describe both lists and which applies where. The in-tree webserver README
(lines 282-287) already lists the correct four; it is *not* drifted here.

### A2. `[x]` `12-webserver-api.md:493` and `19-authentication.md:346` — false accusation against the webserver README

Both docs carry a note telling the reader the in-tree
`controllers/webserver/README.md` has "a drifted STUN list" and to prefer the arch docs.
Per A1 the README's STUN list is the accurate one. Remove the STUN half of both notes.

The *other* half of the accusation (the removed `auth/oauth_status` polling flow) is
correct — but the right resolution is to fix the README (see B1), not to leave a
standing disclaimer. Once B1 lands, both notes go away entirely.

### A3. `[x]` `19-authentication.md:16` — scope count is wrong

**Says:** "Twenty scopes plus two special members."

**Source:** `music_assistant_models.auth.Scope` has **21 members total**: 19 real scopes
plus `ALL` and `UNKNOWN`. The doc's own table lists exactly those 19 real scopes, so the
prose contradicts the table beneath it.

**Fix:** "Nineteen real scopes plus two special members (`ALL` and `UNKNOWN`), 21 in total."

### A4. `[x]` `04-player-controller.md:361-369` — stale player config category table

**Says:** five categories, including `"playback" | Volume normalization, crossfade`.

**Contradicts:** `02-configuration.md:186` ("Volume normalization and crossfade used to
live here under a `"playback"` category; both are now per-queue settings") and
`02-configuration.md:236` (`volume_normalization_target` is "a **global** `streams` setting,
not a player one").

**Source:** `rg 'category="' music_assistant/controllers/config/players.py` yields
`announcements`, `generic`, `player_controls`, `protocol_general`, and a per-protocol
`protocol_category`. The only `category="playback"` on a reusable entry is
`constants.py:449` — `CONF_ENTRY_VOLUME_NORMALIZATION_TARGET`, which the streams core
config consumes, not a player.

**Fix:** replace the table with the six real categories, matching `02-configuration.md:186`.
`02-configuration.md` owns the detail; this table should be a short pointer.

### A5. `[ ]` Verified correct — no action

Checked against source and confirmed accurate; recorded so a later pass does not re-verify:

| Claim | Doc | Source |
|---|---|---|
| `EventType` has 30 members (29 + `UNKNOWN`), category split as tabled | 01 | `music_assistant_models.enums.EventType` |
| `ProviderFeature` has 53 members | 15 | same |
| `DB_SCHEMA_VERSION` = 55 (library), 5 (auth) | 08, 12, 19 | `controllers/music/constants.py:12`, `webserver/auth.py:58` |
| models pin is `1.1.173` | 09 | `pyproject.toml:30` |
| 58 providers ship a `setup_flow.py` | 15 | `ls providers/*/setup_flow.py \| wc -l` |
| 20 production plugin providers + `_demo_plugin_provider` | 11 | `grep -l '"type": "plugin"'` → 21 |
| mDNS matrix (10 providers, exact service types incl. AirPlay's four) | 13 | all `manifest.json` |
| UPnP matrix (`dlna`, `samsung_wam`, `roku_media_assistant`) | 13 | all `manifest.json` |
| `HA_ANNOUNCE_INTERVAL` 86400, `UPNP_DISCOVERY_INTERVAL` 300, `RAOP_MAC_PREFIX` regex | 13 | `controllers/discovery/controller.py:42-52` |
| All tasks constants (2 / 250 / 25 / 100 / 0.25 / 10.0) | 20 | `controllers/tasks/constants.py` |
| All analysis constants (2 sessions, 120.0 hang guard, 0.9 ratio, 300/60 idle, 4h budget, 0.250 pace, nice 10) | 16 | `controllers/streams/audio_analysis.py:51-77` |
| Buffer presets 60/300/1200 s, radio 15 s, RAM gates 4/8 GB | 10 | `controllers/streams/constants.py:21-44` |
| All token/join-code constants (30/365/1/90/7 days, 1 h, 12 chars, charset, 8 h) | 19 | `webserver/auth.py:61-77` |
| Sync-group constants and `PROVIDERS_WITH_DYNAMIC_LEADER_SWITCH` = airplay/snapcast/sendspin | 06 | `providers/sync_group/constants.py` |
| Managed-pool sizing 25/50/250, `CACHE_FORMAT_VERSION` 1, `PLAYBACK_START_TIMEOUT` 5.0, `QUEUE_CACHE_SAVE_DELAY` 5 | 09 | `controllers/player_queues/constants.py:59-82` |
| `CONFIGURABLE_CORE_CONTROLLERS` — the nine listed, in order | 00, 02 | `constants.py:305-315` |
| `DEFAULT_PROVIDERS` — all 12 entries and their mDNS flags | 15 | `constants.py:984-1004` |
| `LOCALES` has 38 entries | 14, 21 | `controllers/metadata/constants.py:15` |
| 31 translation files, ~2476 keys, 1 + 10 + 113 `strings.json` | 21 | `translations/`, `strings.json` inventory |
| Webserver route map — every row, incl. `HEAD /`, both `OPTIONS` | 12 | `webserver/controller.py:186-244` |
| `play_announcement(player_id, url, pre_announce, volume_level, pre_announce_url)` | 04 | `players/controller.py:986-993` |
| AriaCast capability flags (play/pause + next/prev, no seek, `can_initiate=False`) | 11 | `providers/ariacast_receiver/__init__.py:150-156` |
| Pre-commit hook ids `check_config_entries`, `check_translatable_labels`, `build_translations_source` | 02, 21 | `.pre-commit-config.yaml` |
| All quoted line counts (player.py ~3050, players/controller.py ~4200, protocol_linking ~2440, streams/audio.py ~3400, auth.py ~2000, mass.py 1344, …) | 03, 04, 05, 10, 12, 19 | `wc -l` |
| Loudness provider caps at 600 audio-seconds | streams README | `providers/loudness_analysis/provider.py:29,86` |

---

## B. In-tree READMEs contradicting the architecture docs

The ownership rule: READMEs own module inventories and config-key lists; architecture docs
own cross-cutting flows and design rationale. Where a README states a *fact* that the code
has since changed, the README changes.

### B1. `[x]` `controllers/webserver/README.md:183-193` — documents a removed OAuth flow

The "Remote Client OAuth Flow" section describes `auth/authorization_url` with
`for_remote_client=true`, a pending OAuth session, and polling `auth/oauth_status`.

**Source:** #5030 retired the `AUTH_SESSION` popup mechanism and deleted
`music_assistant/helpers/auth.py`. `rg 'oauth_status'` over `music_assistant/**/*.py`
returns nothing. `19-authentication.md:285` states this correctly.

**Fix:** delete the section. Remote clients authenticate over the same
`/auth/authorize` → `/auth/callback` flow; the redirect target is validated by
`helpers/redirect_validation.py`. Then remove the disclaimers per A2.

### B2. `[x]` `controllers/cache/README.md:23` — stale SQLite memory figures

**Says:** "SQLite with WAL mode, mmap (30GB), a 64MB page cache".

**Source:** `helpers/database.py:105-140` `get_sqlite_memory_settings()` scales both to host
RAM (16 KiB–1000 MiB page cache, 256 MiB–2 GiB mmap), and its own comment says "the previous
30GB request was already effectively ~2GiB". `02-configuration.md:408` describes this
correctly.

**Fix:** replace the fixed figures with a pointer to the RAM-scaled helper.

### B3. `[x]` `providers/sendspin/README.md:50-168, 215` — documents a WebRTC signalling API that does not exist

The README's "WebRTC Connection (Remote/NAT Traversal)" section documents four API
commands — `sendspin/ice_servers`, `sendspin/connect`, `sendspin/ice`,
`sendspin/disconnect` — plus a 50-line TypeScript client example and an
`aiolibdatachannel` dependency.

**Source:** `rg '"sendspin/' --glob '*.py' music_assistant/` returns nothing;
`rg 'api_command\(' providers/sendspin/*.py` returns nothing; the provider manifest's
`requirements` are `aiosendspin[server]==7.0.0` and `av==16.1.0` only, with no
`aiolibdatachannel`.

Remote Sendspin access now runs through two mechanisms the arch docs describe correctly:
the authenticated `/sendspin` WebSocket proxy (`12-webserver-api.md:471`) and the
remote-access data channel labelled `"sendspin"` (`12-webserver-api.md:394`).

**Fix:** replace the WebRTC section, the command table, the TS example and the dependency
line with a short description of the two real paths, linking to `12-webserver-api.md`.

### B4. `[x]` `providers/spotify_connect/ARCHITECTURE.md:46` — "Live Inputs" node

**Says:** the AudioSource is "a single live item browsable under the global 'Live Inputs' node".

**Contradicts:** `11-plugin-system.md:155` — #3964 replaced that node with root-level
placement, and only `can_initiate=True` sources are listed at all. Spotify Connect is
`can_initiate=False` (stated two lines later in this same file, and under "Known
limitations"), so it is **not** browsable.

**Fix:** state that it is played through the standard `play_media` flow and is not
browsable, entry coming from the Spotify app.

### B5. `[x]` `providers/hue_entertainment/README.md:53, 88, 97` — stale beat-detection description

Three places say beat detection comes from bass energy spikes in the spectrum, and list
"more precise beat detection using the MA audio analyzer controller" as future work.

**Source:** `providers/hue_entertainment/analyzer.py:4-7,22,266` — the analyzer renders from
a **paced `BeatTiming` schedule** (`aiosendspin.models.visualizer.BeatTiming`) that arrives
from the server in advance. `bridge.py:146-147` requests `types=["beat", "peak", "spectrum"]`
with the comment "Peaks requested as a fallback for when beats aren't computed yet". Bass
now drives *saturation*, and the spectrum drives *brightness* — neither is the beat source.

The README's own architecture diagram (line 14) already says "beat schedule", so the file
also contradicts itself. `16-audio-analysis.md:353` and `11-plugin-system.md:547` describe
the current behaviour correctly.

**Fix:** correct the three stale statements; keep the diagram.

### B6. `[x]` `controllers/streams/README.md` — four small drifts

| Line | Wrong | Right | Source |
|---|---|---|---|
| 119 | `select_flow_format` | `select_flow_pcm_format` | `controllers/streams/audio.py:1330` |
| 214 | "Plugin sources \| No \| Real-time audio (microphone, aux)" | `AUDIO_SOURCE` items — the `PluginSource` model is gone (#3938) | `10-streaming-pipeline.md:570`, `11-plugin-system.md` |
| 173-178 | Analysis-provider table omits `acoustid_lookup` | add it | `providers/acoustid_lookup/`, `16-audio-analysis.md:277` |
| 57 | `fades.py — Fade curve generation` | `SmartFade` ABC plus `SmartCrossFade` / `StandardCrossFade` | `17-smart-fades.md:192` |

### B7. `[x]` `providers/airplay/README.md:27, 136-144` — mDNS subscription list incomplete

Both the component diagram and the "MDNS Service Discovery" section list only
`_airplay._tcp` and `_raop._tcp`.

**Source:** `providers/airplay/manifest.json` declares **four**:
`_companion-link._tcp.local.`, `_mediaremotetv._tcp.local.`, `_airplay._tcp.local.`,
`_raop._tcp.local.` — which `13-discovery.md:110` documents, calling out that the first two
are what make native Apple TV transport controls possible (#4882). The README's own
"Independent device control" section (line 505) depends on exactly those records.

**Fix:** list all four in both places.

---

## C. Coherence between architecture documents

### C1. `[ ]` No contradictions found between architecture documents

Every cross-document pair covering a shared mechanism was checked. Ownership is clean:

| Mechanism | Owner | Others link to it |
|---|---|---|
| `AudioSource` model, plugin taxonomy | 11 | 03, 04, 07, 08, 09, 10, 15 |
| Volume routing, mute lock, group volume | 07 | 03, 04, 06 |
| Scope model, roles, tokens, impersonation | 19 | 01, 02, 04, 08, 12, 18, 20 |
| Transport, routes, dispatch, WebSocket | 12 | 01, 02, 14, 18, 19, 21 |
| Session lifecycle, grouping models | 06 | 03, 04, 05 |
| Per-queue config resolution | 02 | 09, 10 |
| Smart fades analysis / execution split | 16 / 17 | 10 |
| Task system vs `create_task` vs `TaskManager` | 20 | 01 |
| Translation resolution | 21 | 02, 12, 14, 15, 20 |

The one place two documents deliberately restate the same paragraph — the
silence-during-pause contract, in `10-streaming-pipeline.md:284` and
`11-plugin-system.md:342` — already carries an explicit ownership marker ("See
10-streaming-pipeline.md, which owns this note"). Leave as is.

`04-player-controller.md`'s category table (A4) was the only genuine cross-document
contradiction found.

---

## D. Mechanical checks

### D1. `[ ]` Forward references — all resolve

Script-verified across all 43 files (23 arch docs + 9 controller READMEs + 11 provider
docs): every relative link points at a real file and every anchored link at a real
heading. The forward links earlier phases were permitted to leave dangling
(`17-smart-fades.md`, `18-ai-and-mcp.md`, `19-authentication.md`,
`20-background-tasks.md`, `21-localization.md`) all now resolve.

### D2. `[ ]` Key Files paths — all resolve

Every backticked source path in every arch doc's Key Files table resolves. The 22
apparent misses from the automated scan are all intentional non-paths: glob patterns
(`providers/*/manifest.json`), placeholders (`controllers/<name>/strings.json`),
API command names (`providers/icon`, `providers/manifests`), dotted attribute references
(`helpers/util.TaskManager`), a `::` symbol reference, and four references to files
deliberately described as deleted (`helpers/auth.py`, `controllers/config.py`,
`controllers/music.py`, `controllers/metadata.py`, `models/smart_fades.py`).
`scripts/check_config_entries` resolves to `scripts/check_config_entries.py`.

### D3. `[ ]` README catalog — matches the file set

`docs/architecture/README.md` lists all 23 documents (00–21 plus itself), the nine
in-tree controller READMEs (exactly the nine that exist), and outbound links to root
docs, provider docs, `.github/`, and tests — all verified present on disk. The reading
paths still describe what the documents contain.

### D4. `[ ]` Mermaid — 31 blocks, no syntax risks, prose agrees

Scanned all 31 blocks for unquoted labels containing `:`, `(`, `)`, `[`, `]`, `#`:
none found (the `06-grouping.md` quoting fix from the earlier phase held). Each diagram
was read against its surrounding prose during the read-through; the startup-sequence
diagram in `00-overview.md`, the discovery diagram in `13-discovery.md`, the pipeline
diagram in `10-streaming-pipeline.md` and the resolution-chain diagram in
`03-player-model.md` all match their text and the code.

---

## E. Could not verify / deliberately left open

- **Frontend-side claims.** `12-webserver-api.md:427` says
  `helpers/resources/commands_reference.html` renders a dead `required_role` badge. The
  file exists and contains the template, but whether the badge is genuinely unreachable
  depends on the JSON the generator emits at runtime; not exercised.
- **External service behaviour.** The Lokalise round trip (`21-localization.md`), the
  signalling server's close-code semantics (`12-webserver-api.md:388`), and the
  MusicBrainz mirror's rate limit (`14-metadata.md:221`) are all asserted from code
  comments and workflow files, not observed.
- **`docs/architecture/README.md` top-level diagram** draws `PLG --> Players`. Since #3938
  plugin audio reaches players through Music → Queues → Streams rather than directly.
  Left unchanged: it is a deliberately loose orientation diagram, and plugins do also
  create players (`hue_entertainment`). Flagging rather than silently redrawing.
- **`06-grouping.md:96` vs `sync_group/README.md:346-349`.** The arch doc says
  `playback_state` and `elapsed_time` come from the leader's `state.*` while
  `current_media` / `active_source` come from raw attributes, and explains why. The README's
  table says "raw `state.playback_state`", mixing both terms in one phrase. Same
  behaviour, sloppy wording. Not corrected — it is the README's own table and the
  distinction it is trying to draw is already stated correctly in its prose above.

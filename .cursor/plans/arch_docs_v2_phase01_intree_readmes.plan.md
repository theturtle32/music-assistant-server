---
name: arch_docs_v2_phase01_intree_readmes
overview: Phase 1, first pass. Upstream ships README.md files inside controller and provider directories, and 11 of the 20 have drifted from the code next to them. Fix those before the architecture docs start linking to them, so the two layers agree from the outset. This is the only phase that edits files under music_assistant/.
todos:
  - id: batch1_players
    content: "Batch 1: controllers/players, providers/universal_player, providers/sync_group — protocol linking retention, derived_from, and the sync group session lifecycle"
    status: completed
  - id: batch2_streams
    content: "Batch 2: controllers/streams — rewrite the analyze-callbacks section for the passive observer model and fix the file inventory, loudness cap, and config table"
    status: completed
  - id: batch3_webserver
    content: "Batch 3: controllers/webserver — password hashing, Remote ID, JWT token model, scope-based auth, roles, file inventory"
    status: completed
  - id: batch4_providers
    content: "Batch 4: providers/sendspin, providers/airplay, providers/local_audio, providers/hue_entertainment — bridge lists and inventory touch-ups"
    status: completed
  - id: batch5_layouts
    content: "Batch 5: controllers/music, controllers/player_queues — package layout gaps"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only in-tree README/ARCHITECTURE files, commit and push
    status: completed
isProject: false
---

# Phase 1 — Refresh stale in-tree READMEs

Upstream maintains `README.md` files inside most controller directories and several provider
directories. Our architecture docs are going to **link to them** rather than duplicate their module
inventories, which only works if they are accurate. Doing this first means every later phase can cite
them with confidence.

This is the only phase that touches `music_assistant/`. Keep the edits surgical and in upstream's
voice — these files ship to upstream, so they should read like upstream wrote them.

## Audit result

All 20 in-tree docs were audited against sibling code at `76422b305`. A `find` sweep confirmed there
are no others (excluding `**/bin/README.md` and `providers/sonic_analysis/vendored_clap/README.md`,
which are third-party notes).

| File | Verdict | Fix size |
| --- | --- | --- |
| `providers/sync_group/README.md` | **severely stale** | section rewrite |
| `controllers/streams/README.md` | significant drift | section rewrite |
| `controllers/webserver/README.md` | significant drift | section rewrite |
| `providers/universal_player/README.md` | significant drift | few paragraphs |
| `controllers/players/README.md` | minor drift | few paragraphs |
| `providers/sendspin/README.md` | minor drift | few paragraphs |
| `providers/airplay/README.md` | minor drift | few paragraphs |
| `controllers/music/README.md` | minor drift | one line |
| `controllers/player_queues/README.md` | minor drift | one line |
| `providers/local_audio/README.md` | minor drift | one line |
| `providers/hue_entertainment/README.md` | minor drift | one line |

**Confirmed accurate — do not touch:** `controllers/metadata/`, `controllers/cache/`,
`controllers/discovery/`, `controllers/tasks/`, `providers/smart_fades/`,
`providers/itunes_podcasts/`, `providers/gpodder/`, `providers/profiler/`, and
`providers/spotify_connect/ARCHITECTURE.md`.

Churn on upstream-owned files makes the PR harder to accept, so leave those nine alone. The commit
message should record that they were verified, so a later reader knows the audit was complete rather
than partial.

## Batch 1 — player and protocol model

Edit these three together; they describe overlapping behavior and must agree.

### `providers/sync_group/README.md` (severely stale)

Every claim about the lifecycle predates #3947.

1. **`PlayerFeature.POWER` is not always supported.** The base features list claims it is;
   `supported_features` defaults to `{PLAY_MEDIA}` and adds POWER **only** when the raw config
   `CONF_POWER_CONTROL == PLAYER_CONTROL_FAKE` (`player.py` ~126–143).
2. **The lifecycle is session-driven, not power-driven.** Groups **form on play / play_media** via
   `_form_syncgroup()`. `stop()` **dissolves immediately** unless pinned by fake power
   (`_attr_powered is True`). A natural transition to IDLE waits `IDLE_GRACE_SECONDS` (10s) before
   dissolving. Leader removal re-forms after `REFORM_DEBOUNCE_SECONDS` (2s)
   (`player.py` ~366–392, ~1253–1370; `constants.py`).
3. **`_attr_powered` is not the canonical active signal.** The state table and lifecycle prose treat
   it as such; the code uses **`is_active_session`** — sync leader set, idle grace pending, or reform
   pending — for session and active-group semantics (`player.py` ~90–104, mirrored in the base
   `Player` model ~2489–2493).
4. **"Sync leader selected when the group is powered on"** is wrong. The leader is selected in
   `_form_syncgroup()` on playback start; explicit power only exists under fake power control.

This is the same correction Phase 5 makes in `06-grouping.md`. Get both right and consistent.

### `providers/universal_player/README.md`

1. **Native takeover is not unconditional.** The README says a native provider replaces the universal
   player with all protocols linked. `_check_replace_universal_player()` can **retain** the universal
   player when a protocol link is refused, migrating only what moved
   (`protocol_linking.py` ~1017–1023, #4413).
2. **`derived_from` is undocumented.** Output protocol entries carry it for derived transports such as
   Sendspin bridges (`protocol_linking.py` ~1268–1283).
3. **Protocol linking coverage is thin** — no mention of `_link_derived_protocols_of` or the
   underlying-player edges bridges rely on.

### `controllers/players/README.md`

Same two issues, in the controller's own words: the universal→native promotion is oversimplified
(`active_protocol_ids - moved_protocol_ids` governs retention), and `derived_from` on
`OutputProtocol` is missing — for example a Sendspin bridge riding on AirPlay records either
`"native"` or the underlying player id.

Coordinate with Phase 6, which documents derived transports in `05-protocol-linking.md`.

## Batch 2 — streaming and analysis pipeline

### `controllers/streams/README.md`

The **"Analyze Callbacks"** section describes a push model that no longer exists, and the framing
leaks into the overview and pipeline sections (roughly lines 29, 111, 121, 133–148).

1. **Analysis is a passive observer.** `AudioBuffer.get_buffer()` →
   `mass.streams.audio_analysis.start_analysis()` → `AudioAnalysisController._buffer_reader_worker()`
   reading `read_chunk_for_analysis()`, with loudness and smart fades running as separate **audio
   analysis providers** and receiving `process_pcm_chunk()`. There is no `attach_loudness_analyzer`;
   the buffer only exposes `register_cancel_callback()`.
2. **Loudness cap is wrong** — the README says up to 2 minutes;
   `LoudnessAnalysisProvider.MAX_DURATION_SECONDS` is 600.
3. **Smart fades beat detection is wrong** — the README describes librosa on the intro and outro; the
   provider uses Beat This! (`providers/smart_fades/provider.py`).
4. **File inventory is stale** — missing `audio_analysis.py`, `audio_processing.py`, `strings.json`,
   and the icons; it lists `smart_fades/analyzer.py`, which does not exist. The real `smart_fades/`
   tree includes `planner/`, `renderer.py`, `structure.py`, `vocal.py`, `bands.py`, and `filters.py`.
5. **Config table incomplete** — missing keys including `smart_fades_log_level` and the fixed-gain
   normalization keys present in `strings.json` / `constants.py`.

`AudioAnalysisController` should be named as a core streams component. Cross-check against
`providers/smart_fades/README.md`, which is already accurate and is a good model for the corrected
description. Phases 8 and 9 depend on this file and our docs agreeing.

## Batch 3 — auth and remote access

### `controllers/webserver/README.md`

1. **Password hashing is PBKDF2, not bcrypt.** `BuiltInAuthProvider._hash_password()` uses
   `hashlib.pbkdf2_hmac("sha256", …, iterations=100000)` with salt `f"{user_id}:{server_id}"`
   (`auth_providers.py` ~491–502). Note our `12-webserver-api.md` already says PBKDF2 correctly — the
   README is the wrong one here, so fix in that direction.
2. **Remote ID is not `MA-XXXX-XXXX`.** `get_or_create_remote_id()` derives a 26-character base32
   string from the WebRTC DTLS certificate SHA-256 fingerprint
   (`helpers/webrtc_certificate.py` ~184–202).
3. **Token model is outdated.** The README describes `secrets.token_urlsafe(48)` access tokens and
   10-year long-lived tokens. Tokens are **JWTs** issued via `JWTHelper`; long-lived is
   `TOKEN_LONG_LIVED_EXPIRATION` = 365 days; short-lived slides 30 days under a 90-day
   `TOKEN_ABSOLUTE_MAX_EXPIRATION`.
4. **Authorization framing is inconsistent.** The security and request-flow sections say "role-based"
   and "check auth/role", but enforcement is `required_scope=Scope.…` per command
   (`websocket_client.py`, `auth_middleware.py`'s `ROLE_SCOPES`). Roles map to scopes; the API gates
   on scopes.
5. **Roles incomplete** — only ADMIN and USER are documented; `UserRole` also has `GUEST` and
   `SERVICE`.
6. **File inventory incomplete** — missing `sendspin_proxy.py`, `helpers/ssl.py`, `strings.json`, and
   icons.

Coordinate with Phase 14, which builds `19-authentication.md` on the same facts.

## Batch 4 — provider bridge and inventory touch-ups

### `providers/sendspin/README.md`

- File inventory missing `bridge_manager.py`, `bridge_role.py`, `synchronizer_role.py`, `security.py`,
  `helpers.py`, `constants.py`, and icons.
- The external bridges table lists only AirPlay. Implemented bridges also include **local_audio**,
  **chromecast**, and **msx_bridge** (`**/sendspin_bridge.py` under each).
- Bridge linking is described as MAC matching only; the AirPlay bridge header documents
  derived-transport / underlying-player linking.

### `providers/airplay/README.md`

- File inventory missing `control_player.py`, `dashboard.py`, `sendspin_bridge.py`, `strings.json`,
  and icons.
- Same MAC-only bridge linking wording to correct.
- The behavioral claims (250/500 ms start lead, `--protocol auto`, flow mode, PTP daemon, DACP,
  pairing) were verified accurate — leave them.

### `providers/local_audio/README.md`

`coreaudio_volume.py` exists (CoreAudio hardware volume via ctypes) but is not listed and, more
interestingly, **is not imported anywhere in the tree**. The README's "software volume only" claim for
macOS matches current runtime behavior, so it is not wrong — but the orphan module is undocumented.
Decide deliberately: either add an inventory line noting it is currently unused, or leave the README
alone and flag the dead module to the user. Do **not** describe it as active.

### `providers/hue_entertainment/README.md`

The file-structure table labels `__init__.py` as "Config flow (pairing, settings)". Pairing lives in
`setup_flow.py`; `__init__.py` is the provider setup entry point. Everything else (in-process
`register_external_player`, the 30 Hz loop, `hue_latency_ms`, effect modes) matches the code.

## Batch 5 — controller layout gaps

- `controllers/music/README.md`: the package layout omits the `recommendations/` sub-package
  (`controller.py`, `library.py`, `__init__.py`) and `recency.py`. Phase 10 documents both — this is
  just the inventory line.
- `controllers/player_queues/README.md`: the module layout omits `config.py`, which holds the core and
  per-queue config-entry schemas the controller delegates to.

## Style

- Match each file's existing structure, heading style, and tone. Do not reformat or restructure a file
  to fix a paragraph.
- Fix what is wrong and add what is materially missing. Resist expanding these into full architecture
  documents — that is what `docs/architecture/` is for.
- No changelog or "updated for PR #NNNN" annotations inside the READMEs; that belongs in the commit
  message.

## Verification

- Re-read each edited file end to end; a section rewrite in `sync_group` or `streams` can easily leave
  a contradicting sentence in an overview or state table elsewhere in the same file.
- `pre-commit run --all-files`.
- `git diff --stat` should show **only** `README.md` files under `music_assistant/` — no code, and
  nothing under `docs/`.

## Commit

```
docs: refresh stale in-tree controller and provider READMEs

Phase 1 of the architecture docs refresh. Corrects in-tree documentation
that drifted from the code alongside it, ahead of the architecture docs
starting to reference these files as the canonical module inventories.

Sync group's lifecycle description predated the move to session-based
grouping, the streams README still described push-based analysis
callbacks, and the webserver README misstated password hashing, the
remote ID format, and the token and authorization models.

Verified as already accurate and left unchanged: metadata, cache,
discovery and tasks controllers; smart_fades, itunes_podcasts, gpodder
and profiler providers; spotify_connect's ARCHITECTURE.md.
```

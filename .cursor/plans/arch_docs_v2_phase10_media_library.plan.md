---
name: arch_docs_v2_phase10_media_library
overview: "Phase 10. Refresh 08-media-library.md for the music controller package: overhauled search with per-provider timeouts and FTS5 trigram indexing, external ID lookup table, slim summary list mode, event suppression during sync, schema v55, and the new recommendations and recency subsystems."
todos:
  - id: preflight
    content: "Pre-flight: verify the music package layout, search flow, MediaControllerBase surface, and DB schema against the working tree"
    status: pending
  - id: structure
    content: "08-media-library.md: replace the monolith description with the package layout plus RecommendationsController and RecencyEngine; link to the in-tree README"
    status: pending
  - id: search
    content: "08-media-library.md: rewrite the search section (cache tiers, soft/hard timeouts, FTS5 trigram, plugin search providers, exact-match shortcut, sound effects)"
    status: pending
  - id: base
    content: "08-media-library.md: refresh MediaControllerBase (removed abstract method, external_id_lookup, deferred commits, summary mode, collections, user provider filter)"
    status: pending
  - id: schema
    content: "08-media-library.md: rebuild the SQLite schema section for v55 including new tables, FTS tables, and column additions"
    status: pending
  - id: sync
    content: "08-media-library.md: correct the library sync flow for event suppression and batched commits"
    status: pending
  - id: subcontrollers
    content: "08-media-library.md: extend the sub-controller specializations (tracks, audiobooks, playlists, genres)"
    status: pending
  - id: recommendations
    content: "08-media-library.md: add the recommendations subsystem section (controller, library rows, payload mixin, lastfm provider)"
    status: pending
  - id: recency
    content: "08-media-library.md: add the recency engine section and its consumers"
    status: pending
  - id: helpers_providers
    content: "08-media-library.md: add collections, cue sheets, track filter, dynamic playlists, and a short new-provider-ecosystem note; refresh Key Files"
    status: pending
  - id: verify
    content: "pre-commit, confirm the diff touches only docs, commit and push"
    status: pending
isProject: false
---

# Phase 10 — Media library

File: `docs/architecture/08-media-library.md` (60–70% rewrite).

Related in-tree README: `music_assistant/controllers/music/README.md`, which upstream keeps current
and which covers the package layout, the one-way dependency rule (sub-controllers never import
`MusicController`), the database split via `MusicDatabaseSetupMixin`, and the migration
backup/reset-on-failure policy. **Link to it for the module table**; our doc owns the recommendations
API, recency engine, search architecture, summary modes, FTS indexing, collections, user-scoped
playlog, and plugin providers in browse/search — none of which the README covers.

## Structure (#4266)

`controllers/music.py` plus `controllers/media/` became `controllers/music/` with `controller.py`,
`constants.py`, `database.py`, `helpers.py`, `migrations.py`, `recency.py`, `media/`, and
`recommendations/`. The constructor now also builds
`self.recommendations = RecommendationsController(...)` and `self.recency = RecencyEngine(...)`.

Update every path: `controllers/media/base.py` → `controllers/music/media/base.py`,
`controllers/media/genres.py` → `controllers/music/media/genres.py`, and so on.

## Search (#4671, #4681)

The doc describes a simple flow ending in "results are cached for 600 seconds". Current behavior:

- Combined results cached 600s **only when all providers succeed**
  (`SEARCH_CACHE_EXPIRATION_COMBINED`).
- Per-provider cache: 24h for streaming, 15min for local (`SEARCH_CACHE_EXPIRATION_*`).
- Soft timeout 8s (`SEARCH_PROVIDER_SOFT_TIMEOUT`) with the background search continuing; hard
  timeout 120s.
- Plugin providers with `ProviderFeature.SEARCH` are included via
  `get_unique_providers() + plugin_search_providers`.
- New `providers` parameter; `library_only` is deprecated.
- A near-exact library match can skip the provider search entirely (`_get_covered_media_types`).
- `SearchResults.sound_effects` is populated (#4669).
- Sorting moved to `controllers/music/helpers.py` as `sort_search_result` (was `_sort_search_result`
  on the controller).
- Library search **does** query genres — the doc's claim that genres are excluded is wrong
  (`MediaType.GENRE` appears in `result_fields`).
- Library search uses FTS5 with a trigram index, minimum 3 characters
  (`search_name_match_clause` in `helpers.py`).

## `MediaControllerBase`

- The `radio_mode_base_tracks` abstract method was **removed** (dynamic radio moved to the plugin
  layer, #4498). Still abstract: `_add_library_item`, `_update_library_item`, `match_providers`.
- Add to the core methods table: `update_item_in_library` (provider write-back plus artwork
  invalidation), `set_external_ids`, summary-mode `library_items(summary=True)` (the default),
  `collapse_collections`, `played_only`, `in_library_only`.
- **External ID matching** now goes through an indexed `external_id_lookup` table rather than
  embedded JSON (#4628, #4645).
- Writes are batched with `database.deferred_commit()` (#4584), and the
  `SUPPRESS_MEDIA_ITEM_UPDATES` ContextVar suppresses per-item events during bulk sync (#4578) —
  which contradicts the library-sync sequence diagram's per-add `MEDIA_ITEM_ADDED` / `UPDATED`
  events.
- **Summary / slim list mode** (#4693, #4679): `summary=True` by default with a `summary_item_cls`,
  for performance on large libraries. Worth its own short subsection.
- `get_unique_providers()` also applies the **user `provider_filter`** for non-admin users, not just
  streaming-domain dedup.
- Note there is no `_get_provider_mapping` method (old or new) — provider selection is
  `_select_provider_id()`, now user-filter-aware with a plugin fallback. Do not introduce the wrong
  name.

## Browse

Root browse also surfaces `ProviderFeature.AUDIO_SOURCE` plugin providers, promotes a single
initiable source to a playable item, and applies the user provider filter. Cross-link Phase 12.

## SQLite schema

`DB_SCHEMA_VERSION = 55`, defined in `controllers/music/constants.py`, with migrations in
`controllers/music/migrations.py` (rejects `prev_version < 15`, backs up, resets on failure).

- **Removed:** `loudness_measurements` and `smart_fades_analysis` are no longer library tables.
  Loudness, beats, and related data live in `audio_analysis`; smart fades analysis is
  provider-domain based under the streams controller.
- **Add:** `settings` (schema version), `external_id_lookup`, `audiobook_artists`,
  `audio_analysis_failures`, and the `{table}_fts` FTS5 virtual tables per `MEDIA_ITEM_DB_TABLES`.
- **Column additions:** `playlog` gained `userid`, `queue_id`, `user_initiated`, `playback_speed`,
  an `artists` JSON column, and a per-user UNIQUE constraint; `playlists` gained `is_dynamic`,
  `supported_mediatypes`, `translation_key`; `artists` gained `artist_type`; `genres` gained
  `content_type`, `is_excluded`, `is_default`, `genre_aliases`.

## Sub-controller specializations

The doc covers only Tracks and Artists. Add:

- **Tracks:** `library_items(explicit=...)` filter (#4597); summary mode by default (#4693).
- **Audiobooks:** authors and narrators, collections, the `audiobook_artists` table (#3569, #3570).
- **Playlists:** dynamic playlists (`is_dynamic`), localized names.
- **Genres:** the `content_type` taxonomy (#4435, #4474).

## Recommendations (new section)

`controllers/music/recommendations/` — `RecommendationsController` serving
`music/recommendations` and `music/recommendations/items`, with built-in library rows
(Recently played, In progress, …) in `library.py`, provider row interleaving, timeouts, and the user
provider filter on item fetch (#4487).

Also cover `RecommendationPayloadMixin` (`models/recommendation_payload.py`) — stale-while-revalidate
bulk payload caching used by Tidal, Deezer, Apple Music, Plex — and note that
`lastfm_recommendations` is a **`MetadataProvider`** with `ProviderFeature.RECOMMENDATIONS` seeded
from the playlog (#4457), not a music provider. Phase 11 mentions it from the metadata side; keep
one authoritative description here and cross-link.

## Recency engine (new section)

`controllers/music/recency.py` — `RecencyEngine` / `RecencySnapshot`, batched playlog reads
producing song and artist recency with fuzzy cross-provider song keys. Consumers: smart shuffle
(#4475, Phase 7), smart playlist dedup, and dynamic radio (#4498).

## Helpers, dynamic playlists, provider ecosystem

- `helpers/collections.py` and `collapse_collections`; `helpers/cue_sheet.py` (local file metadata
  enrichment); `helpers/track_filter.py` (the advisory filtering ContextVar used by dynamic
  playlists — cross-link Phase 7).
- Dynamic playlists as library rows: `playlists.is_dynamic` written by the `smart_playlist` and
  `radio_playlist` plugins (#4498). Cross-link Phase 12/13.
- **User-scoped library access:** provider filters, per-user playlog, API scopes (#4613) — a short
  paragraph cross-linking Phase 14.
- Short new-provider note (classification only, no deep dives): music providers `ambient_sounds`,
  `rain_mood`, `pocketcasts`, `sverigesradio`, `filesystem_google_drive`, `filesystem_onedrive`,
  `qqmusic`, `nts`, `teddycloud`; plugin providers `smart_playlist`, `radio_playlist`; metadata
  providers `playlist_metadata`, `wikipedia`, `lastfm_recommendations`.
- Refresh Key Files with the package paths plus `database.py`, `migrations.py`, `constants.py`,
  `helpers.py`, `recency.py`, `recommendations/`, and the in-tree `README.md`.

Also fix the `02-configuration.md` DB table list if Phase 3 left anything inconsistent — the schema
is authoritative here.

## Verification

- `rg "DB_SCHEMA_VERSION|external_id_lookup|SUPPRESS_MEDIA_ITEM_UPDATES|deferred_commit|SEARCH_PROVIDER_SOFT_TIMEOUT|search_name_match_clause|RecencyEngine|RecommendationsController"`.
- Confirm removals: `rg "radio_mode_base_tracks|loudness_measurements|smart_fades_analysis"`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): media library refresh for the music package, search and recommendations

Phase 10 of the upstream/dev refresh.
```

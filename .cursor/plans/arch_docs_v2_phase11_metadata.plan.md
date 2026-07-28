---
name: arch_docs_v2_phase11_metadata
overview: "Phase 11. Refresh 14-metadata.md for the metadata mixin package, the opaque image-ID proxy that replaced query-string URLs, corrected provider priority ordering, the Wikipedia and playlist_metadata providers, colour palette extraction, LRC normalization, and the genre taxonomy split."
todos:
  - id: preflight
    content: "Pre-flight: verify the metadata package layout, provider priorities, imageproxy behavior, and radio artwork pipeline against the working tree"
    status: pending
  - id: package
    content: "14-metadata.md: replace the monolith description with the mixin package layout; link to the in-tree README"
    status: pending
  - id: priorities
    content: "14-metadata.md: correct the provider priority ordering and add a priority column to the capabilities table"
    status: pending
  - id: enrichment
    content: "14-metadata.md: fix Phase 2 gating for tracks, derived-genre masking, and add the artist description selection policy"
    status: pending
  - id: imageproxy
    content: "14-metadata.md: rewrite the image proxy section for opaque image IDs, allowed sizes, and dynamic route registration"
    status: pending
  - id: thumbnails
    content: "14-metadata.md: fix the thumbnail cache key and add the shared source-image cache; correct the collage story"
    status: pending
  - id: palette
    content: "14-metadata.md: add a colour palette extraction section and cache invalidation"
    status: pending
  - id: providers
    content: "14-metadata.md: add Wikipedia and playlist_metadata; correct the MetadataProvider ABC surface and the MusicBrainz rate limit and path"
    status: pending
  - id: lyrics
    content: "14-metadata.md: fix lyrics provider ordering and add LRC normalization"
    status: pending
  - id: radio_genres_tasks
    content: "14-metadata.md: correct the radio artwork cache key and lookup pipeline, the genre taxonomy split, the maintenance schedule, and the locale count"
    status: pending
  - id: verify
    content: "pre-commit, confirm the diff touches only docs, commit and push"
    status: pending
isProject: false
---

# Phase 11 — Metadata

File: `docs/architecture/14-metadata.md` (40–60% rewrite). Round 1 refreshed this doc against a
structure that predates the package split (#4265) and the imageproxy redesign (#3960, #4544); those
two areas account for most of the drift.

Related in-tree README: `music_assistant/controllers/metadata/README.md`. Link for the module map.

## Package layout (#4265, #4838)

`controllers/metadata.py` is now `controllers/metadata/`, where `controller.py` composes
`ImageProxyMixin`, `RadioArtworkMixin`, and `MetadataEnrichmentMixin`, alongside `constants.py`,
`enrichment.py`, `helpers.py`, `images.py`, and `radio.py`.

`post_setup()` registers the **dynamic** route `/imageproxy/*` on both the webserver and the streams
server. Cross-link Phase 14, which fixes the route map in `12-webserver-api.md`.

## Provider priority (ordering is wrong in the doc)

`providers` sorts **ascending** by `priority` (lower first). Current values: Fanart.tv **10**,
TheAudioDB **20**, Wikipedia **25**, iTunes **30**, default **50**, `playlist_metadata` **90**.

So Fanart and TheAudioDB run **before** iTunes. Round 1 changed this text to "iTunes Artwork
first… then Fanart.tv" — that was wrong and needs reverting with the real ordering. Add a priority
column to the Provider Capabilities table so the ordering is checkable at a glance.

## Enrichment

- **Phase 2 for tracks:** the doc says tracks are always attempted when online metadata is enabled.
  Tracks are subject to the same 90-day refresh gate as everything else — online providers run only
  on `force_refresh` or `needs_refresh`.
- **Local genre masking:** for artists and albums, **propagation-derived** genre mappings also count
  as local (`has_derived_genre_mappings`, #3883, #3815). Tracks still only check
  `track.metadata.genres`.
- **Artist descriptions (new):** bios are **excluded** from the generic field merge. Candidates are
  collected from music providers then metadata providers, and `_select_description` picks a winner:
  preferred language → keep an existing preferred-language bio → English → highest-priority
  candidate (#3972).
- **Playlists:** `_update_playlist_metadata` aggregates genres from tracks and calls providers with
  `ProviderFeature.PLAYLIST_METADATA`. It no longer calls `create_collage_image`; the doc's claim
  that the handler "generates collage images" is obsolete.

## Image proxy (rewrite)

- URL form is now the opaque `{base_url}/imageproxy/{image_id}?size=&fmt=` where
  `image_id = sha256(provider + path)`, with `proxy_id` injected on outbound `MediaItemImage`
  serialization. Only server-registered IDs resolve. The old
  `?provider=&path=` form with double-URL-encoded paths was **removed** (#3960, #4544, #4550).
- Allowed sizes are whitelisted: `{0, 80, 160, 256, 512, 1024}`; anything else returns 400 (#4897).
- Document `compute_image_id` / `resolve_image_id`, the cache category used for the mapping, and the
  security rationale for opaque IDs.

## Thumbnails, source cache, collages

- Cache key is `{sha256}_{size}_v2[_flat].{jpg|png}` — versioned — not
  `SHA256("{provider}/{path}")_{size}.{ext}`.
- Beyond the memory LRU and disk tiers there is a **source-image cache** (memory byte budget plus
  on-disk `{hash}_src`, 1h TTL for remote URLs) shared by thumbnails, palettes, and collages (#4703).
- Add `invalidate_image_cache()` — busts thumbnails and palettes when a local file changes.
- Collages: the primary path is now the `playlist_metadata` plugin with multiple templates, storing
  images in provider storage. `create_collage_image` still exists in `images.py` but is not invoked
  from enrichment, and the `collage_images/` directory is residual. Say so rather than implying the
  controller generates collages.

## Colour palette (new section)

`helpers/colors.py` plus the `metadata/get_image_palette` API. Palettes attach asynchronously to
players via `PlayerController._schedule_palette_fetch` and surface as `current_media.palette`
(#4193, #4550, restricted to opaque image IDs). Cross-link Phase 4, which adds `palette` to
`MEDIA_IDENTITY_KEYS`.

## Providers

- **`MetadataProvider` ABC** has more than the four documented methods: also
  `get_playlist_metadata`, `get_similar_tracks`, `get_similar_artists`, `get_recommendations`,
  `get_recommendation_items`, `get_artist_toptracks`, `get_artist_topalbums`. Features include
  `PLAYLIST_METADATA`, `RECOMMENDATIONS`, `SIMILAR_*`, and `ARTIST_TOP*`.
- **Wikipedia (new, #3972):** artist bios via MBID → MusicBrainz relations → Wikidata sitelinks,
  priority 25.
- **`playlist_metadata` (new, #3786, #4460, #4593):** `PLAYLIST_METADATA`, priority 90, multiple
  artwork templates, skips provider-owned playlists, optional genre detection, hourly cleanup task.
- **`lastfm_recommendations`:** a `MetadataProvider` serving Discover rows, not library enrichment.
  Phase 10 owns the authoritative description — cross-link, don't duplicate.
- **MusicBrainz:** the mirror rate limit is `ThrottlerManager(rate_limit=10, period=10)` — 10
  requests per 10 seconds, not 5/s — and the provider is now a package,
  `providers/musicbrainz/` (#3905). Fix the path.

## Lyrics

Providers are iterated **sorted by priority**, not in load order. On-demand responses pass through
`normalize_lrc_lyrics()` from the new `helpers/lyrics.py` (#4823).

## Radio artwork, genres, maintenance

- **Cache key** is `f"{artist}|{track}|{album_key}"` where
  `album_key = create_safe_string(album_name)`, not `f"{artist}|{track}"`.
- **Lookup pipeline additions:** `normalize_radio_artist_name()` before lookup; singles tried before
  albums; album-name reordering within each type; artist splitting via `split_artists`; album from
  stream metadata refining artwork (#4364). Provider order follows priority: Fanart → TheAudioDB →
  iTunes. Round 1's caller analysis is still correct — keep it, and add that ICY may prefer StreamUrl
  cover art over a MusicBrainz lookup.
- **Genres:** the controller path is `controllers/music/media/genres.py`, and there are now three
  taxonomies — `genre_mapping.json`, `podcast_genre_mapping.json`,
  `audiobook_genre_mapping.json` — with icons in a flat directory plus `podcast/` and `audiobook/`
  subdirectories (#4611, #4474). Genre metadata is owned by `GenreController`, not
  `MetaDataController`; make that ownership explicit and cross-link Phase 10.
- **Maintenance tasks** are no longer all scheduled at 4:00 AM local. Each gets a **random UTC
  time** spread across the day (#4126). The playlist scan excludes dynamic playlists
  (`is_dynamic = 0`).
- **Locales:** the doc says "30+"; `constants.py:LOCALES` has 38 (including `zh_TW`, #4870).
- Optionally note `get_diagnostics` and the tolerance for corrupt metadata JSON in scan tasks
  (#4803), cross-linking Phase 16.

## Verification

- `rg "compute_image_id|resolve_image_id|invalidate_image_cache|normalize_lrc_lyrics|normalize_radio_artist_name|has_derived_genre_mappings|_select_description"`.
- Confirm the priority values by reading each provider's `priority` attribute directly.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): metadata package, opaque image proxy and provider priority fixes

Phase 11 of the upstream/dev refresh.
```

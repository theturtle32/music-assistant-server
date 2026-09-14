# Metadata controller

Enriches library items with metadata from the music and metadata providers, resolves and serves
images, and looks up artwork for radio streams.

## Deep dives

- [Image proxy and palettes](images.md): the opaque image proxy, thumbnails, and colour palettes.
- [Genres and metadata](genres.md): aliases, the three taxonomies, and the scanning pipeline.

## Package layout

The controller is composed from mixins, each in its own module, mirroring the player controller.
All behaviour is reachable on the single controller instance; the split is only for organising a
large surface.

| Module | Role |
|---|---|
| `controller.py` | Lifecycle, config entries, preferred-language handling, the enrichment entry point, maintenance tasks |
| `images.py` | Image resolution, the opaque image id system, thumbnail rendering and caching, the proxy endpoint, palettes, playlist collages |
| `radio.py` | Resolving radio artwork by matching now-playing metadata against the library and online sources |
| `enrichment.py` | The per-media-type routines that merge provider metadata into library items |
| `helpers.py` | Pure functions that need no controller instance |
| `constants.py` | Config keys, cache categories, task ids, the locale map, proxy tunables |
| `strings.json` | Translatable strings for this core module |

The `strings.json` is only discovered because the controller lives in its own folder; the
translation build concatenates one per controller directory under that controller's namespace.

## Local beats online

Provider mappings are processed in priority order, so local sources win over streaming and online
ones. Online metadata is fetched only when enabled and, for most types, only when an item actually
needs a refresh. Online genres are not merged on top of locally-supplied ones when the user prefers
local genres.

## Refresh interval

Enrichment for a given item re-runs at most every 90 days unless a refresh is forced. The online
services here are free and shared, and keeping load off them is the point. Artist biographies are
re-derived on each refresh and picked by a preferred-language-first fallback.

## Radio artwork

Stations send free-form "artist and title" strings with no agreed separator or order. The radio
subsystem normalizes and heuristically re-orders the names before matching them against the library
and online sources, and caches both hits and misses so a station that never matches does not hammer
the providers on every track change.

## Maintenance tasks

The daily tasks, meaning the missing-artist-metadata scan, the playlist refresh and the
thumbnail-cache cleanup, run at a **randomized** time drawn once per process rather than at a fixed
hour. Independent installations would otherwise all hit the same shared online mirror at the same
moment.

Album reconciliation instead runs hourly. It re-enriches a bounded batch of albums whose type is
still unknown and that are due a refresh, which typically means they were created from a sparse
provider search result during a sync, then re-runs provider matching now that full album details
are available.

A confirmed match belonging to another duplicate album is folded in through the safe merge path, so
duplicates self-heal without ever auto-adding new library items. A transient failure simply retries
at the normal refresh cadence rather than needing a retry journal of its own.

## Related architecture docs

- [Media library](../../../docs/architecture/media-library.md) for how enrichment fits library
  assembly.
- [Providers](../../../docs/architecture/providers.md) for the metadata provider type and its
  features.
- [Players](../../../docs/architecture/players.md) for how a palette reaches a player's display.

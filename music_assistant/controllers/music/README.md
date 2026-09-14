# Music controller

Aggregates and normalizes media items from every music provider into the SQLite library database,
and is the central entry point for library access: search, browse, recommendations, library edits
and playback bookkeeping.

## Deep dives

- [search.md](search.md): the search flow, the full-text index, and URI parsing.
- [sync.md](sync.md): sync scheduling, bulk writes, deletion handling, provider removal.
- [schema.md](schema.md): tables, the playlog, migrations, and dev versus stable numbering.
- [recommendations.md](recommendations.md): row aggregation, library rows, the recency engine.
- [media/README.md](media/README.md): the per-media-type sub-controllers and the matching rules.

## Package layout

- `controller.py`: the `MusicController`, a core controller holding the orchestration logic and
  composing the per-media-type sub-controllers.
- `database.py`: `MusicDatabaseSetupMixin`, mixed into the controller. Owns the library database
  lifecycle: connection setup, schema creation, maintenance. Kept separate because the schema code
  is large and self-contained, and it carries no state of its own.
- `migrations.py`: the versioned schema migration steps, kept out of `database.py` as an injected
  function so this large block stays self-contained and individually testable.
- `media/`: the per-media-type sub-controllers.
- `recommendations/`: the aggregating recommendations sub-controller.
- `recency.py`: the shared recency engine.
- `constants.py`: config keys, the database schema version, background task ids and tuning values.
- `helpers.py`: stateless helpers used by the controller.
- `strings.json`: translatable strings for this module.

## Design notes

**Layering.** The controller orchestrates and the sub-controllers hold the type-specific logic. The
sub-controllers never import the controller back, which is what keeps import cycles out.

**Library data model.** Library items use the provider id `library`, and provider mappings record
which provider items a library item resolves to. A library item never has a mapping to itself.
Maintenance prunes orphaned mappings and playlog rows.

**Startup order.** The database is initialized first through the mixin, then maintenance tasks are
registered and provider syncs are scheduled. Setup also finishes any provider removal that a
restart interrupted.

## Provider orchestration

Fetching an item checks the library for a row matching that provider and item id, and returns the
library item when there is one, optionally scheduling a background metadata refresh. Otherwise it
resolves the provider instance and asks it directly.

For an item available from several providers the library stores one canonical row plus one mapping
per provider. Non-unique streaming mappings are cloned across all instances of the same domain, so
a second account on the same service inherits the first one's mappings. Cloned mappings are marked
so they can be told apart from mappings the item was genuinely added on, which both album track
import and sync deletion rely on. A recurring task re-runs the cloning over the whole library so
mappings created before a second instance existed catch up.

One instance per streaming domain is queried for search and lookups, while every instance of a
non-streaming provider is queried. A streaming provider's catalog is far larger than the user's
library, so a second account adds duplicates rather than coverage, whereas a local provider's
catalog is its library and each instance may point somewhere different.

## Dynamic playlists are library rows

A dynamic playlist is not a separate concept here. It is an ordinary playlist row with the dynamic
flag set. Two plugin providers write them: one rule-based, where the flag decides whether tracks
are re-evaluated on every play or frozen once, and one that renders a seed as a playlist.

Everything downstream treats them like any other playlist. Only the queue controller reads the
flag, to decide whether to run a bounded managed pool instead of a linear enqueue.

## User-scoped access

The library is read through a per-user lens. Which music sources a user can reach follows from the
owner and sharing setting carried by each source rather than from an allow-list on the user, and
the resulting set applies to the provider lists, to browse, to recommendations and to every library
listing. It also steers which mapping an item's details are fetched from, so playback uses the
listener's own accounts first and never one that was not shared with them. Plugin providers are
never restricted.

Play history, resume positions and recency are scoped by user. An explicit provider request is
intersected with what the user can reach, and an empty intersection raises rather than silently
returning nothing.

## Related architecture docs

- [Media library](../../../docs/architecture/media-library.md) for the big picture of how a library is assembled.
- [Providers](../../../docs/architecture/providers.md) for the provider interface, features and load lifecycle.
- [Playback](../../../docs/architecture/playback.md) for how library items reach a queue and a speaker.
- [Plugins](../../../docs/architecture/plugins.md) for audio sources, dynamic playlists and plugin-contributed rows.

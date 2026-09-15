# Media sub-controllers

One sub-controller per media type, all sharing `MediaControllerBase`. The base class is generic
over its item class and owns the library interaction pattern; each subclass adds the type-specific
queries and relations. Subclasses never import `MusicController` back, which keeps the dependency
direction one way.

## Deep dives

- [Matching and merging](matching.md): match and store, merging, external ids, and the comparison
  APIs.

| Module | Media type |
|---|---|
| `base.py` | `MediaControllerBase`, shared by all of the below |
| `artists.py` | Artists, including audiobook authors and narrators |
| `albums.py` | Albums |
| `tracks.py` | Tracks |
| `playlists.py` | Playlists, including the dynamic ones |
| `radio.py` | Radio stations |
| `audiobooks.py` | Audiobooks |
| `podcasts.py` | Podcasts and their episodes |
| `genres.py` | The genre taxonomy |

## What the base class gives you

The base class registers the per-type API surface in its constructor, so a new media type gets
count, listing, fetch, update and remove commands without declaring them. Most of the public
surface is final. Subclasses customize through the two query properties, the row parse hooks, and
their own add and update implementations, rather than by overriding public methods.

A subclass must implement three things: adding a library item, updating a library item, and
matching the item against other providers.

Every listing funnels through one query builder that composes the filters, the fast random path,
collection collapsing and the final select. Two choices there are worth knowing about before you
change them. Provider and in-library filters are correlated subqueries rather than a join with a
group-by, and the group-by is only added when a caller supplied joins that can fan rows out. Both
exist so SQLite can stream from a sort index instead of materializing and sorting the whole result.

### Summary mode

List endpoints return summary items by default. A summary selects only what a list view needs and
builds a slim item class rather than hydrating a full media item. Internal callers that need
metadata, artists or album relations opt back into the full object.

The summary query deliberately selects the normalized search and statistics columns even though a
list view does not display them, because the sort keys order on them and they have to be resolvable
from the result set. Availability is recomputed from the provider mappings, because a summary item
cannot inherit the full item's availability logic.

### Reachable via

Restricting a listing to items with an available mapping to given provider instances answers a
different question from "is this in my library". A library assembled from several services still
lists items a particular service cannot play, which is wrong for a row scoped to one provider and
wrong for a user who was only shared some of them. An explicit empty list means "restrict to no
providers" and returns nothing; no list at all means "do not restrict". Callers have to respect
that difference. Counts apply the same access rules, so a count never disagrees
with the list it labels.

### Collections

Collapsing collections groups library items that share a collection name, so an audiobook series
appears once instead of as every book in it. The composed query is wrapped in a CTE that aggregates
rows per collection name, and sorting is restricted to the subset of sort keys that survive the
aggregation. Collection item ids encode the media type and the collection name, which is how a
fetch routes back to the owning sub-controller. Audiobooks are currently the only type wired up.

## Matching

Adding an item to the library is a match-first operation: an incoming provider item joins an
existing row when it shares a mapping, an external id or a confident name match, and becomes a
new row otherwise. The rules, the merge semantics and the three comparison APIs are in
[Matching and merging](matching.md).

## Event suppression during bulk work

A context variable suppresses the per-item added and updated events. A full library sync would
otherwise emit one event per touched item, serialized once per connected client. While suppressed,
an update also skips writing the change back to the provider, because during a sync the update came
from that provider. Two callers set it: the provider sync handler and provider cleanup. Deletions
are never suppressed. Clients follow progress through task events and refresh once when the sync
completes.

## Type-specific notes

**Artists** carry a type that distinguishes singers from audiobook authors and narrators, so an
artist listing does not mix them. Removing an artist cascades to albums and tracks that have no
other artist references.

**Albums** assemble their tracklist across every provider holding the album, and where the same
track is offered by more than one, **a playable copy displaces an unplayable one**. Services grey
out individual tracks on an otherwise available album, so without that the tracklist a user sees
depends on which provider happened to be read first. Each track keeps its position in the result
while its content is replaced, so the running order does not shuffle as copies are substituted.

**Audiobooks** treat authors and narrators as first-class artists, while keeping the plain string
columns for providers that only supply names. Reads prefer the linked artists and fall back to the
strings, and the sync snapshot records which shape is stored so a sync can tell when an upgrade is
needed. Search runs the normal indexed pass first and appends an author and narrator scan when the
first page came back thin.

**Radio stations** can be dynamic, meaning the provider generates the content on demand rather than
pointing at a fixed stream. Being dynamic disables name-based linking in both directions. Two
providers offering a station called "Chill" are offering the same broadcast when it is a real
stream, and two entirely different generators when it is dynamic, so the ordinary cross-provider
merge would produce a station that plays the wrong thing.

**Playlists** record which media types they can hold, so adding an unsupported type is rejected. A
provider-supplied name can carry a translation key and parameters so it survives the library round
trip localized, and updates adopt a synced item's key and parameters as a unit rather than mixing
an old key with new parameters. Migration copies a playlist onto another provider or into managed
storage, matching each track through the graded comparison and reporting what was approximated.

Only a playlist **this server owns** carries its own access record. A provider's playlist follows
the sharing of the music source it came from, and trying to share one directly is refused saying
so, because two answers to "who may see this" would inevitably disagree.

Sharing one is the owner's call: another member cannot, and changing the owner needs the
library-management scope, which is also what lets an administrator repair a playlist they cannot
themselves see. A playlist with no owner is a playlist of the whole home, and must therefore be
shared with somebody, since a private one nobody owns would be reachable by nobody at all.

Two rules exist because accounts change. Owners and shared members **keep their place while their
account is disabled**, so disabling somebody does not quietly rewrite everyone else's sharing. And
when a user is deleted, the playlists it owned become playlists of the whole home rather than
vanishing, while it is dropped from the share list of every other playlist.

**Genres** are the only editable taxonomy here, and the largest sub-controller. Spoken-word
taxonomies are namespaced separately from music, so a podcast "Comedy" never merges into the music
"Comedy". Aliases let many provider genre strings resolve onto one canonical genre. Exclusions hide
a genre without deleting it, with per-item overrides for derived mappings. A scheduled scan
re-derives mappings across the library, using a short-lived name lookup so a running sync picks up
user edits without re-querying per item.

## Related architecture docs

- [Providers](../../../../docs/architecture/providers.md) for the provider interface these
  controllers fetch through.
- [Overview](../../../../docs/architecture/overview.md) for where the music controller sits.

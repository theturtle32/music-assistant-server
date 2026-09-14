# Recommendations and recency

Part of the [music controller](README.md).

## The recommendations sub-controller

`recommendations/` owns the API and produces no rows of its own. It gathers rows from every
provider that declares the feature, which can be a music, metadata or plugin provider, and
interleaves them one folder per source per pass so no single provider monopolizes the top of the
page.

Rows and items are separate calls. The listing has to be cheap enough to render a Discover page
immediately, and each row's contents are fetched as it scrolls into view. Row fetches are bounded
by a short timeout because rows are contractually cheap with no live backend calls, and item
fetches by a longer one. A timeout or error yields an empty list, so one misbehaving provider
degrades to a missing row rather than a failed page.

The item call re-applies the user's provider filter and re-checks that the provider still declares
the feature. Without that, a user could reach into a provider an admin restricted them from by
calling the items endpoint directly with a row id.

## The library rows are a provider too

The library rows are no exception to the aggregation: they come from a builtin plugin provider
whose only declared feature is recommendations. The controller has no library-specific branch left.

Moving the rows out means they compose through the ordinary provider machinery, meaning feature
declaration, the user filter and timeout isolation, rather than needing a parallel path, and it
lets the rows be reordered or extended without touching this controller.

Rows cover in-progress items, recently played, recently added, favorites, random picks, forgotten
and rarely played items, and most played. Rows that are interesting to some libraries and noise in
others ship disabled by default.

Library rows support the provider filter through the reachable-via listing filter, which is what
lets a user restrict "recently added" to a single service. A provider's own rows cannot offer that.

## Bulk payloads

Most streaming providers get their recommendations from one bulk backend call, and a mixin factors
that out: the provider implements only the payload fetch, and the mixin derives both the rows call
and the per-row items call from it.

Caching is stale-while-revalidate on two layers, in memory and in the cache database, so a cold
instance after a restart warms from cache with at most one read. Concurrent callers share one
shielded fetch, so a caller that times out cannot cancel it for the others.

The mixin cancels in-flight work on unload, which is why it has to be listed before the provider
base class for that override to be reachable at all.

## The recency engine

`recency.py` answers "was this heard recently" fast and in bulk. Smart shuffle, dynamic playlist
deduplication and dynamic radio refills would otherwise issue one playlog query per candidate
track.

One batched, user-scoped query returns an immutable snapshot. Lookback windows are configurable per
dimension, a disabled window drops that dimension, and if all are disabled the query is skipped
entirely.

The snapshot indexes plays three ways, which is what makes cross-provider matching work:

| Index | Keyed on | Catches |
|---|---|---|
| Exact identity | Provider and item id | The track's own id and every one of its provider mappings, so a play from another account still counts |
| Fuzzy identity | Normalized title and artist | A remaster, a single versus album edit, or differing artist credits across providers |
| Artist | Lowercased artist name | Artist plays, which are keyed by library id, so the name is the only portable key |

Rows written before the artists column existed contribute no fuzzy key, and regain one on the next
play.

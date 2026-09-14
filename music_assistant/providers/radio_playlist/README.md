# Endless Mix Playlists

A builtin, always-on plugin that turns any media item into an endless mix: a dynamic playlist
blending the seed's own tracks with tracks similar to them. It is what replaced the old radio mode.

It declares **no provider features at all** and implements only the playlist pair, which is enough
because those two methods are not feature-gated. A useful thing to know when writing a plugin that
wants to contribute media without claiming a whole capability.

## The seed is the id

The generated playlist's item id **is the seed item's own URI**, so the playlist URI round-trips
straight back to the seed with nothing persisted anywhere.

That is the whole trick. There is no table of generated stations, no cleanup when a seed is
deleted, and no identity to keep in step with the library, because the id is derived rather than
allocated. A seed can be an artist, album, track, genre or playlist.

The result is an ordinary playlist row with the dynamic flag set, so the queue treats it exactly
like a provider station or a rule-based smart playlist. See
[controllers/music](../../controllers/music/README.md).

## Building a batch

Seeds are expanded into base tracks first: an artist contributes its top tracks, anything else
contributes the tracks it would play. A bounded random sample of those becomes the base set, which
both seeds the similarity lookups and gets interleaved into the result in a fixed pattern so the
mix keeps returning to familiar ground.

Two details are worth knowing.

**A single track seed is random-walked rather than looked up once.** One track yields one
deterministic similar list, so every refill would return the same batch. Walking the similarity
graph outward from the seed instead keeps successive batches different.

**A consumer may publish a filter that this provider pre-applies** to the base sample, so tracks
the queue would discard anyway are skipped before the expensive similarity lookups. If filtering
would leave nothing to work with, the unfiltered sample is kept, because an empty mix is worse than
one containing something the consumer will drop.

Similar-track lookups are tried without a provider round-trip first and only then with one, so a
library that already holds the answer never pays for the network call.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for plugins that implement music features.
- [Playback](../../../docs/architecture/playback.md) and
  [controllers/player_queues/continuation.md](../../controllers/player_queues/continuation.md) for
  the bounded pool that consumes these playlists.
- [Media library](../../../docs/architecture/media-library.md) for dynamic playlists as library
  rows.

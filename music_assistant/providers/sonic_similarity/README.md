# Sonic Similarity

Finds tracks that *sound* like a given track, using the audio analysis already stored by the
[sonic_analysis](../sonic_analysis/) provider rather than by tags, genres or collaborative
filtering.

It is a plugin that behaves like a music provider: it declares the search feature and nothing else,
which is enough to make it a source of similar tracks for the dynamic queue and for recommendations.
That is the pattern that makes plugins a genuinely open extension point rather than an audio-only
one; see [plugins](../../../docs/architecture/plugins.md).

It depends on the analysis provider, since it indexes what that provider produces and has nothing
to index without it.

## Two engines, two kinds of similar

Both are nearest-neighbour indexes over the same library, and they answer different questions.

| Engine | Vector | Answers |
|---|---|---|
| Traits | A small signature assembled from the analysis scalars: tempo, energy, loudness and the rest, weighted by a configurable preset | "Another track with this shape": similar tempo and intensity |
| Character | A large audio embedding the analysis provider already stored | "Another track with this character": timbre and texture, closer to how a listener would describe it |

Traits is always on and cheap. Character is opt-in, because building and holding a second index
over high-dimensional vectors costs memory and rebuild time that a small library does not need.

The important thing about Character is that it adds **no new analysis work**. The embeddings are
already computed and stored during ordinary playback analysis, so enabling it builds an index over
data that exists rather than scheduling a scan.

## Rebuilds are atomic

An index is rebuilt rather than mutated, and the new one is swapped in once complete, so a query
arriving mid-rebuild reads the old index rather than a half-built one. Rebuilds are serialized by a
lock, and a failure leaves the previous index in place.

When the optional index is enabled but unavailable, queries against it raise a localized error
naming the situation rather than silently falling back to the other engine, because the two answer
different questions and quietly substituting one would be misleading.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for plugins that implement music features.
- [Providers](../../../docs/architecture/providers.md) for dependencies and feature flags.
- [controllers/streams/analysis.md](../../controllers/streams/analysis.md) for where the analysis
  and the embeddings come from.
- [Media library](../../../docs/architecture/media-library.md) for how similar-track lookups feed
  recommendations and dynamic queues.

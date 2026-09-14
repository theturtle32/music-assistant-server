# Image proxy and palettes

Part of the [metadata controller](README.md).

## Opaque image ids

Images are addressed by an opaque, deterministic id derived from the provider and the path, not by
a query string carrying those values.

**This is a security boundary, not a cosmetic change.** Only ids the server itself has registered
resolve to anything, so the endpoint cannot be coerced into fetching an arbitrary URL on a caller's
behalf. Image paths are frequently URLs, sometimes carrying credentials, and they now never appear
in a client-visible query string.

The id is exposed to clients as a field on the image model, injected during outbound serialization.
The mapping is registered when the id is generated, written through an in-process cache in front of
the cache controller, so resolving a freshly generated id never blocks on SQLite.

The proxy route is registered on both the main webserver and the streams server. Which base URL an
image URL uses depends on who will fetch it: player-facing media URLs point at the streams server,
everything else at the webserver.

## Colour palettes

A palette is derived from artwork so clients and players can theme a now-playing view to the
current track. It carries a primary and accent colour plus foreground and background colours for
light and dark contexts.

Extraction quantizes the source image for candidate colours, then picks and adjusts them so every
contrast pair required by the spec clears the accessibility floor. The picker aims higher than the
floor first and falls back to it.

Two adjustments in there are deliberate and easy to undo by accident. Contrast for the dark
on-light colour is **capped** as well as floored, because otherwise near-black image regions such
as text outlines or letterboxing win and the result is pure black rather than a vivid dark shade
taken from the artwork. And accent selection requires a minimum distance from the primary colour,
so the two do not collapse into the same colour.

### Caching and concurrency

Palettes are content-addressed on the same provider and path hash, and stored in the cache
controller for 90 days, so they survive restarts and are shared process-wide.

An empty result is deliberately **not** cached. An empty palette usually means a transient decode
or download failure, which should be retried rather than remembered.

Concurrent extraction for the same image is deduplicated through a keyed task, and the CPU-bound
work runs in a thread.

### Reaching a player

Palette resolution is asynchronous but player state serialization is synchronous, so the palette is
carried on the player rather than resolved inline. The player controller kicks off extraction when
the current media has no palette yet, resolves the proxy URL back to a provider and path, and
applies the result only while the URL still matches.

The controller also prefetches the next queue item's palette so it is hot at the transition, and
skips players that mirror a parent's media entirely, since resolving per group member would be
duplicated work.

Because the palette lands a moment after the track change, it counts as part of the media identity
a player compares against. A player pushing colours to a display needs a second callback once the
palette arrives, and it would not get one otherwise.

## The palette API

The palette command takes an opaque image id only, the same one a client already holds on its image
model, and returns nothing for anything unregistered. That keeps it from becoming a
fetch-arbitrary-URL primitive, exactly as the proxy endpoint does.

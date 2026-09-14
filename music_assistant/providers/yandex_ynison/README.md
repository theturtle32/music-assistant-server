# Yandex Music Connect (Ynison)

Makes a Music Assistant player appear as a selectable device inside the Yandex Music app, over the
Ynison protocol.

## It is a receiver that fetches its own audio

Every other receiver has audio pushed into it. This one does not: Ynison is a control protocol, not
an audio transport.

The plugin follows Ynison state to learn *which track* the app is playing, then resolves that
track's stream through the companion Yandex Music provider. Its declared dependency on that music
provider is therefore load-bearing rather than cosmetic: without it there is no way to get the
audio at all.

That has a visible consequence. **Its capability flags are computed, not fixed**: pause, seek and
track skip are offered only while the music provider is actually loaded, and the source is rebuilt
whenever that changes. A user who unloads the music provider sees a source that can still be
selected but no longer controlled.

## One session, many tracks

It is the only receiver whose stream is **multi-track**. A single generator session streams the
current track, waits for a track-change event, streams the next, and keeps going until the source
is deselected.

Everywhere else a track boundary ends the stream. Here it does not, because the session models the
app's playback rather than one file, and tearing down per track would gap the audio.

Transport commands are translated into Ynison peer commands rather than acted on locally.

Volume is **not** synchronized in either direction. There is no outward volume hook, which is
deliberate rather than missing: the Yandex device has its own level and no echo-suppression
problem needs solving here.

## Pinning to one player

A config option keeps the source on one configured player rather than letting the app move it.

When it is on and a selection arrives for a different player, the selection is redirected to the
configured target **and then rejected**. The rejection is what aborts the wrong player's stream;
the redirect is what makes the right one start.

The redirect is issued at most once per idempotency window, and that bound is necessary rather
than defensive. The target may be a bridge or a sync group whose stream is consumed under a player
id that never equals the configured target, so every redirect re-triggers selection. Re-issuing the
play command on each rejection would turn that into an unbounded storm.

## Format is frozen per session

The PCM format is captured when a session starts, so reloading the provider mid-session takes
effect on the next session rather than causing a sample-rate mismatch part-way through a stream.

The format object handed out is a fresh copy, because the shared one is mutated in place by the
transcoding layer and sharing it would leak that mutation into every later stream.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the audio source model and the receiver
  patterns this one breaks from.
- [Providers](../../../docs/architecture/providers.md) for how a declared dependency on another
  provider behaves at load time.
- [Playback](../../../docs/architecture/playback.md) for realtime sources in the pipeline.

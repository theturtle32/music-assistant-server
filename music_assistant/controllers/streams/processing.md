# Normalization, crossfade and overlay

Part of the [streams controller](README.md). This covers what happens to the audio once for the
whole queue stream. For what happens per destination on the way out, see [output](output.md).

## Volume normalization

Normalization levels perceived loudness across tracks from different sources. The configured mode
is per queue, the target loudness is a global setting on this controller, and the fallback modes
resolve down to a concrete one depending on whether a stored measurement exists. Radio and tracks
carry separate preferences.

| Mode | Behaviour |
|---|---|
| Disabled | Nothing is applied |
| Dynamic | Levels in real time |
| Measurement | A static gain derived from the stored measurement and the target |
| Fixed gain | A constant adjustment from config |
| Source | The provider already delivers levelled audio, so nothing is applied |

The mode resolves twice, once when stream details are built and again after loudness hydration,
because a measurement may land in between.

The source mode is an outcome rather than a choice. A provider reports that it already delivers
normalized audio, and applying normalization on top would level already-levelled audio, so the
chain stays empty and the mode records why. Crossfade has the same counterpart for providers
handing over already-crossfaded audio, such as a DJ mix or a continuous stream. Both add no filter,
so neither defeats bit-perfect detection the way an active stage would.

Measurement comes from the builtin loudness analysis provider; see [analysis](analysis.md).
Loudness supplied externally, by file tags, ReplayGain or a provider's own figure, is written under
a virtual provider domain that wins the priority walk.

## Crossfade

Crossfade is queue-scoped. The toggle and the mode are per queue with a global default, while the
duration is global only, because a numeric range cannot carry the tri-state option that a per-queue
override needs.

The effective mode is resolved in one place. Smart crossfade is the default when it is available
and is only honoured when available, so anything else lands on the standard crossfade. Availability
requires both a buffer preset with room for the analysis window and the smart fades analysis
provider to be loaded.

A transition is vetoed when either side is not a track, when there is no next item, when both
tracks belong to the same album unless the user opted in, and, outside flow mode, when the two
tracks have different sample rates and the player has not opted in. There is no reliable way to
detect a gapless album, so album-internal transitions are left alone by default.

Pending crossfade data is discarded when the user seeks into a track, or when the next item changed
while the crossfade was being prepared.

### Build, then mix

The mixer builds before it mixes. Building picks the implementation and primes its filters without
touching a byte of audio, walking a degradation chain that ends at the standard crossfade, which
never fails. The smart path needs beats on both tracks and falls back immediately without them.

The fallback deliberately keeps the outgoing track's analysis rather than discarding it: the
standard crossfade uses it to work out how much of the tail to retain so an audible vocal is not
clipped, instead of blindly stripping trailing silence.

The buffered tail is capped at half the track duration and abandoned below a few seconds, where it
would not be musically meaningful.

Analysis and execution are separate concerns. The optional provider produces the signals and this
package consumes them; see [providers/smart_fades](../../providers/smart_fades/README.md) for the
planner, the filters and the renderer.

## Audio overlay

A per-queue overlay mixes a looping sound effect into the queue's audio. Mixing happens once per
queue stream, so every synced player consuming that stream hears the identical mix.

An active overlay forces flow mode, because the overlay has to play continuously across track
boundaries and that is impossible with per-item stream requests. Radio is the exception, since it
is already one long-lived stream and is wrapped per request instead. The internal format widens for
clipping-free headroom.

Failures degrade rather than interrupt. An overlay source that cannot be resolved means playback
continues without it, and an overlay input that dies mid-stream leaves FFmpeg passing the main
audio through. Music playback is never interrupted by the overlay.

Audio already sitting in a player's buffer is unaffected by an overlay change, which is why the
queue controller restarts playback on an audible change, and for the same reason a seek can shift
the overlay position. That is acceptable for ambient content.

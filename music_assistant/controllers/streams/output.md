# DSP, formats and fidelity

Part of the [streams controller](README.md). This covers what happens per destination on the way
out. For what happens once for the whole queue stream, see [processing](processing.md).

## DSP and output plans

Per-player DSP is applied in the final encoding stage. An output plan returns the executable filter
list wrapped alongside a client-facing description of the same processing, so what a client
displays and what FFmpeg runs come from one place.

The chain runs input gain, then the user's enabled filters, then output gain, then channel
selection.

There is no unconditional limiter at the end. Clipping protection is a filter the user opts into
rather than a fixed cost on every stream. Only filters that actually emit parameters count as
active, so a neutral filter is not reported as a stage and does not defeat bit-perfect detection.

Most filters render to a plain FFmpeg audio filter string. Convolution is the exception, because
its impulse response is a second input, which is why the filter graph builder switches to a complex
filter as soon as one is present. The sound effect overlay uses the same path.

Several flag choices in the filter catalog carry non-obvious reasoning, so read the comments before
changing them. Pitch shifting preserves formants so voices do not sound like chipmunks. The limiter
runs without auto make-up so it stays a transparent ceiling. Stereo widening disables the filter's
internal hard clipping, which would otherwise clamp a widened signal before the output gain could
bring it back down. Crossfeed overrides a default that would attenuate every stream it touches.

### Grouping can suppress DSP

A player in a multi-device group whose members do not support per-device DSP has its DSP reported
as disabled by the group rather than as off, because per-device filters would produce different
audio on each member and break synchronization. That distinction matters to the UI: a config that
is enabled but suppressed reads differently from one the user turned off.

### Shared outputs

One output path can serve several players. A plan resolves its shared destinations, mapping
protocol players onto their user-facing parent, and reports the plan for every one of them.
Synchronized players and sync leaders are included, so a sync group's members all appear on the
shared chain.

Passing an empty set of destinations rather than none marks a path that can gain destinations
later, which is what lets a stored template fan out to players that join mid-stream.

## Format selection

The final output format comes from the requested extension and the player's capabilities. The
content sample rate is used when the player supports it, otherwise its highest supported rate, and
bit depth is then capped by the depths actually paired with that rate rather than by the player's
global maximum, so a player that only does 24-bit at 48 kHz is described correctly. Lossy formats
cap lower.

Non-track media such as radio and announcements is capped by the source's declared depth rather
than the internal PCM depth, because normalization or DSP widens that. A lossy station stays narrow
while a hi-res stream keeps its own depth.

The internal PCM format never upsamples. It takes the highest supported rate at or below the source
rate, and falls back to the lowest supported rate when the source sits below every one of them,
rather than a fixed rate the player may not accept. Bit depth follows the source unless crossfade,
normalization, overlay or DSP is active, where a wider format gives processing headroom. Crossfade
and overlay force stereo, because mixing needs a consistent channel count. Live audio sources
short-circuit to a passthrough at the source's own rate and depth where the player allows it.

Flow mode takes its rate from the player's own flow mode setting rather than a fixed ladder.
Because a flow stream can feed several players it intersects their supported rates and fails when
they share none.

## What is happening to this audio

The processing manager answers that for clients. It tracks processing per queue session and
publishes a complete chain onto each queue item's stream details.

The chain splits the way the work does. Queue processing is what happens once for the whole stream:
the internal format, normalization, playback speed, crossfade mode and overlay. Outputs are what
happens per destination, and players whose effective output is identical collapse into one entry
listing several player ids.

State is keyed by queue and gated on the queue's session, so a superseded producer silently stops
publishing rather than fighting the current one. Housekeeping drops state for items before the
current index and reconciles the output set against the players actually attached, which is how a
player joining or leaving a group updates the chain. Chains are republished only when they changed.

### Fidelity and bit-perfect

Quality is classified from codec semantics, and an output's quality is the minimum of the input and
output quality, because fidelity cannot be gained downstream.

Bit-perfect answers whether the decoded source samples reach the player untouched. It is unknown
until the formats are resolved, and otherwise false unless all of the following hold:

- The output format is lossless. A lossy container is never bit-perfect.
- Sample rate, bit depth and channel count are identical at every stage, including any intermediate
  handoff format a provider path hands audio over in.
- There is no normalization, no playback speed change, no crossfade, and no active overlay.
- There is no effective DSP and no channel mapping. Enabled with no filters and zero gain still
  counts as untouched.
- No stage marked the audio as altered, which stages do when they apply an intentionally invisible
  transform such as a fade-in.

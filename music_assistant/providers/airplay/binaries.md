# The streaming binary

Part of the [AirPlay provider](README.md). Why the actual streaming does not happen in Python, and
how the server drives the process that does it.

## Why not Python

AirPlay needs accurate timestamp handling, realtime packet transmission, low-latency buffering, and
sample-precise agreement across several devices at once. A garbage-collected interpreter on an
event loop shared with a music library is the wrong place for that, and the sync error is audible
when it goes wrong.

So one binary per device handles the protocol, and the server handles everything around it.

## Provenance

A single binary covers every route, selected for the host platform and architecture, and validated
on first use. It is deliberately **not** stored in this source tree or in the Python packages.

Official container builds download the pinned, architecture-specific asset from its own release and
verify it against that release's published checksums. Local development does the same through the
setup script when the binary is absent. See [bin/README.md](bin/README.md).

## Three channels

The server drives the process over three separate channels, and the separation is what makes the
timing work.

**Audio goes in on standard input**, as one persistent stream for the whole process lifetime, in
whichever sample format the device's capability calls for. The binary reads it into a single ring
buffer.

That stream may be written **eagerly, ahead of the scheduled start**, because byte zero maps to the
sample audible at the start instant rather than to "now". A seek or a track change flushes the ring
in place and refills it; the input is never closed between tracks, only the transcode feeding it is
restarted. Closing it ends the stream permanently.

**Commands go in on a named pipe**, out of band from the audio, so a command never has to wait
behind buffered samples. That carries the start instant, the in-place flush, transport actions,
volume, and the now-playing text. Text metadata is sent immediately after the process starts, while
timeline-anchored metadata and artwork are refreshed once the receiver connects.

**Status comes back on the error stream**, normalized into a small set of messages: connected,
playing, paused, flushed, audio, end of stream. The audio message is a one-shot per start cycle,
re-armed by each flush, reporting that the first input bytes arrived. It is what the session waits
on before anchoring, and is the reason no setup time anywhere has to be guessed.

A fourth, informational channel reports the effective lead and the device's buffering window on
standard output, which the server parses and logs for diagnostics.

The server reads the status stream in its own task, using it to update player state, detect that a
connection completed, surface errors and packet loss, and track elapsed time.

## Now-playing metadata

Title, artist, album, artwork and progress are sent to the device: over the stream for ordinary
speakers, and additionally over the modern flow's own metadata channel for an Apple TV, which is
what makes its now-playing screen render.

## Working on it

The binary answers a check argument, which is what validates it on first use and is the quickest
way to confirm a local build works.

Adding a command means changing the binary's own source, which lives in a separate repository, and
then sending the new command over the named pipe from the stream module.

For debugging, verbose logging surfaces the binary's arguments, everything it writes to its error
stream, inbound remote-control requests, connection state changes and packet loss warnings. That is
usually enough to tell a network problem from a pairing problem from a device that simply will not
render at the configured queue depth.

## Related

- [streaming.md](streaming.md) for the start sequence these messages drive.
- [control.md](control.md) for the inbound control channel, which is separate from all of this.

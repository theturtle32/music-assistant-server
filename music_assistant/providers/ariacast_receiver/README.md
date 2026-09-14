# AriaCast Receiver

Receives audio from an AriaCast sender and exposes it as a live audio source.

Unlike the other receivers it wraps no external binary. The AriaCast wire protocol is implemented
natively in Python on top of the HTTP server library the rest of the server already uses, which is
why this provider is a single module rather than a process manager.

## The wire surface

One HTTP server carries the whole protocol, plus a UDP socket for discovery on its own port.

| Route | Carries |
|---|---|
| `/audio` | The inbound PCM stream, as a WebSocket |
| `/control` | Transport commands from the sender |
| `/metadata` | Track info, pushed both ways; also accepted as an HTTP POST |
| `/stats` | Periodic buffer and playback counters, pushed once a second |

Artwork is served over ordinary HTTP GETs alongside those.

Audio is fixed-format stereo PCM at 48 kHz in 20 millisecond frames. Frames land in a queue that
the stream generator drains, so the provider never blocks the socket on a slow consumer. A frame
arriving at an unexpected size is dropped rather than shifting every subsequent sample.

## One sender at a time

A second connection to the audio route while one is already streaming is **rejected outright**
rather than queued or mixed. Two senders interleaving PCM into one queue would produce noise, and
failing the connection tells the second sender immediately.

## Draining around pauses

The generator drains stale frames on both entry and exit.

Without that, a pause leaves frames sitting in the queue that would play out as a burst of stale
audio when the stream resumes, and the built-up latency never recovers on its own. A cold start
that never receives anything fails fast rather than waiting indefinitely.

## Three different player ids

The trap here, and the source of sessions that go sticky after the first one, is that "the player"
is three different things at once.

| | Is |
|---|---|
| The owner | The player the source was selected on, and where the session hangs |
| The session player | The player actually consuming the stream, which may be a protocol player or a sync leader |
| The configured target | Where a new session should land, resolved once and then reused |

**Release against the owner, stop against the session player.** Deselecting the session player
would leave the session attached to an owner nobody released, which is what made a second session
refuse to start. Stopping the owner instead of the player really holding the stream would tear down
a group that should merely pause.

The resolved target is remembered so a later session reuses it rather than resolving again, since
re-resolving mid-life can pick a different player than the one the session is already tied to.

## Control

Pause and track skip are forwarded to the sender as control actions; seeking is not supported.
Seek commands are still acknowledged rather than rejected, because the protocol expects an
acknowledgement and the flag already tells the server not to offer seeking.

A sender that vanishes without saying it stopped is treated as having stopped. Without that the
source stays claimed and the stream generator never exits, so the next session finds the source
still in use.

Audio only flows when a sender connects, so the source cannot be initiated from the server side and
is started by the external app choosing this server.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the audio source model and the receiver
  patterns.
- [Playback](../../../docs/architecture/playback.md) for how a realtime source bypasses the buffer.

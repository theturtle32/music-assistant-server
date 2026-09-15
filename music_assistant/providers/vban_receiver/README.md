# VBAN Receiver

Receives audio over the VBAN protocol, which carries raw PCM over UDP, and exposes it as a live
audio source. It is the simplest receiver in the tree and the most useful one to read first.

There is no metadata channel and no transport control: the source's title and artist are a static
pair built from the stream name and the sender host. Everything interesting about it is
configuration and lifecycle.

## The one receiver the server can start

Every other receiver waits for an external app to pick this server. VBAN is the opposite: **the
server may initiate it**, and an external app may not trigger it.

That follows from what the protocol is. A VBAN sender transmits to an address whether or not
anything is listening, so there is no session to join and nothing announces itself. The server
opens the UDP listener on demand instead, and if the configured sender has not sent a packet within
the first second, the stream request fails with a localized error rather than hanging on silence.

It is consequently the only receiver that appears in the browse tree by default, since browse only
offers sources the server is allowed to start.

## Configuration is the feature

Almost everything is configurable, because VBAN is used to bridge whatever a user already has:
PCM format, sample rate, channel count, the bind address and port, the expected sender host, the
stream name, the receive queue size, and the back-pressure strategy when that queue fills.

Format is not negotiated, so those values have to match the sender.

## Ownership without a stop

The source is exclusive and claims a queue when selected, like the other receivers. What it does
**not** do is stop the previous player.

There is nothing to stop. A passive UDP receiver has no concept of an active playback session on
the far side, so the previous queue's read loop simply notices the ownership change on its own one
second timeout and exits. Sending a stop would be a command to a player that is not producing the
audio.

Selection also records the stream session that claimed it, and release only happens when the
session still matches. A player that drops and reopens the same stream URL would otherwise have the
old request's late teardown clear the live claim of the new one.

The claim is taken at selection rather than when stream details are requested, so a preload path
can ask about the stream without blocking a later handoff to a different queue.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the audio source model, the capability flags
  and the selection lifecycle.
- [Playback](../../../docs/architecture/playback.md) for how a realtime source bypasses the buffer.

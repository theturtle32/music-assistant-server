# AirPlay Receiver

Makes a Music Assistant player appear as an AirPlay destination, so a phone or laptop can send
audio *to* the server. The inverse direction, playing to an AirPlay speaker, is the
[airplay](../airplay/README.md) player provider.

It wraps `shairport-sync` rather than implementing the protocol, running one daemon per connected
player and exposing each as a live audio source. See [bin/README.md](bin/README.md) for the
bundled binaries, which are also found on the system path when not bundled.

## One daemon, one port, per player

Each connected player gets its own daemon, its own pair of named pipes for audio and metadata, and
its own advertised AirPlay port.

**Ports are derived deterministically from the instance and player ids**, not allocated, and they
stay within the AirPlay 2 range. Two reasons, and both matter.

They have to survive a restart, because the AirPlay *player* provider uses them to recognize the
server's own advertisements during discovery and ignore them. A port that moved would make the
server discover itself as a speaker.

And Python's built-in hashing is salted per process, so it cannot be used for anything that must
be stable across restarts. Collisions probe upwards deterministically, over ids visited in sorted
order, so the derivation is the same whatever order the players arrive in.

The set of connected players is fixed for the lifetime of a load; changing it in config reloads the
provider.

## Formats and control

The source advertises the protocol-native lossless format at CD rate for display purposes, while
what the daemon actually writes into the pipe is plain PCM. Those are two separate fields precisely
so a client can show the sender's format rather than the pipe's.

It supports no transport control at all: no pause, no seek, no track skip. The control hook exists
only to satisfy the contract and does nothing. Audio flows only while an AirPlay client is
connected, so requesting a stream with no active client raises rather than returning silence, and
the source cannot be initiated from the server side.

## Volume is inbound only

The receiver does not push volume outward, so it implements no outward volume hook and avoids the
echo problem other receivers have to solve.

Volume arrives from the AirPlay client on the metadata pipe and is applied to the player. The
**first event of each session is skipped**, because it is the daemon's initial sync from its own
configured default rather than anything the user did, and applying it would clobber the player's
current level.

The daemon is configured not to attenuate audio itself, so the level is applied once, by the
server, on its own player.

## Metadata and artwork

Title, artist, album, duration and elapsed time are parsed from the metadata pipe and pushed onto
the source.

Cover art is served through the provider's own image resolution, keyed by a hash of the image
bytes. Each distinct image therefore gets its own cache entry, and a stale request cannot write new
bytes under a key an old image already holds.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the audio source model and the receiver
  patterns this one shares.
- [Playback](../../../docs/architecture/playback.md) for how a live source bypasses the buffer.
- [Players](../../../docs/architecture/players.md) for live source sessions on a player.

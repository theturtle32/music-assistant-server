# Bridges and virtual players

Part of the [Sendspin provider](README.md). Two ways something that is not a Sendspin client ends up
behaving like one.

## Bridging another protocol

Another provider can register one of its players as an external client of the protocol server. The
point is cross-protocol grouping: Sendspin owns timing and synchronization, and the other protocol
carries the audio the last hop to the device.

Registration creates a client on the server, which raises a client-added event, which makes this
provider build a player for it. That player is then linked to the bridged one.

**The link is declared, not inferred.** Before registering, a bridge names the player its new client
rides on, so the resulting player carries a derived-transport edge pointing at it. The player
controller parents them from that edge with no identifier matching involved, and records on the
parent's output entry what the transport was derived from, which is what distinguishes a bridge from
an independently discovered third path to the device.

Bridges additionally register the device's real identifiers for cross-protocol matching, and the
client identity is derived from the device's own hardware address or unique id, so it is stable
across restarts.

A shared manager owns the lifecycle: **a bridge exists only while the player it rides on exists and
is enabled.**

### The bridges that exist

| Bridged protocol | Client id from | Audio path |
|---|---|---|
| AirPlay | Hardware address | Through the bridge into the AirPlay streaming process |
| Local audio | Device unique id | Through the bridge to the local sound card |
| Chromecast | Hardware address, or unique id for cast groups | **Not** through the bridge: the receiver app runs its own Sendspin client, connecting directly |
| TV kiosk | Its own player id | **Not** through the bridge: the kiosk runs a vendored Sendspin client |

That split is the thing to notice before writing a new one. Half of these carry audio and half do
not; where the device can run a client itself, the bridge exists only to make it appear as a player
and to parent it correctly.

### Writing one

Describe the device's capabilities, declare the underlying player and any identifiers **before**
registering, register the external player with a stream-start callback, and either reuse the shared
bridge role to receive audio or write a role of your own.

[airplay/sendspin-bridge.md](../airplay/sendspin-bridge.md) documents a bridge that streams audio,
including what it does when the transport dies. The Chromecast bridge is the worked example of one
that does not.

## Virtual players

A plugin can ask for a hidden, server-side anchor player to host a shared listening session.

A virtual player owns a queue and leads a group, but **renders no audio itself**. Guests are
attached and detached through ordinary grouping and receive the stream, with catch-up for late
joiners.

The reason to have one at all is that the anchor is server-side and lasts for the session's
lifetime, so guests arriving and leaving never trigger a group leader transfer. A session hosted on
a real guest device would collapse when that guest walked out of the room.

Virtual players are hidden from the UI, are not exposed to Home Assistant by default, expose no
volume of their own since member volumes apply instead, and are removed when the owning provider
unloads. Configurations belonging to an owner that no longer exists are swept at startup.

**They are never auto-restored.** When this provider reloads or the server restarts, the owning
plugin has to create its anchor again. Re-creating it with the same id reuses the persisted
configuration, so the restoration is transparent, but nothing happens unless the owner acts. That is
the sharp edge behind the same warning in
[helpers/shared-playback.md](../../helpers/shared-playback.md), which is what most callers use
instead of this API directly.

## Related

- [Protocol linking](../../../docs/architecture/protocol-linking.md) for derived transports.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for cross-protocol
  grouping.
- [Plugins](../../../docs/architecture/plugins.md) for the plugins that host shared sessions.

# Pairing, remote control and volume

Part of the [AirPlay provider](README.md). Everything that travels in the opposite direction from
the audio.

## Pairing

Apple devices must be paired before they can be streamed to, and there are two flavours.

**Modern pairing is delegated to the streaming binary.** The device shows a PIN, the binary runs the
exchange and prints the resulting credentials. Doing it in the binary rather than in Python is
deliberate: it guarantees the pairing identity is byte-identical to the one used to verify at stream
time, which is exactly the class of bug that is miserable to diagnose.

**Legacy pairing is implemented natively**, as a three-step authenticated exchange producing a
client id and secret that are handed to the binary at stream time.

The flow is a config action that starts pairing, the user entering the PIN the device displays, and
a second action that completes it. Credentials are stored per protocol in the player's config.

**The remote-control identifier used during pairing must match the one used during streaming**,
because verification signs with it. A stable identifier derived from the server's own id is used, so
pairing survives a restart.

Credentials for the streaming, control and monitoring planes are kept **separately from each
other**. That lets the monitoring library retain the complete accessory identity it needs without
disturbing the streaming identity, and means a failed monitor does not take down a healthy control
connection or vice versa.

## Remote control from the device

While a stream is active, devices can send control commands back: the buttons on an Apple TV remote,
volume on the device itself, and transport commands.

The provider advertises a control service and runs a small server to receive them. Each session
derives an identifier from the player's hardware address, which is handed to the binary, sent to the
device, and used to match an inbound request back to the right player.

The commands understood are the transport set (next, previous, play, pause, play-pause, stop),
volume up and down, a shuffle toggle, a report of the device's own volume level, and a pair of
signals meaning the device switched to another input or powered off, and that it is available again.

That last pair matters: when a device reports it has switched away, it is removed from the active
session rather than being streamed to silently.

## Volume ownership

An AirPlay volume command sets the **receiver's own** volume, and that level stays behind on the
device after the session ends.

So the server only sends one when nothing else owns the volume of this output. On a device that is
also reachable through a native provider or another protocol, a Sonos speaker or an AV receiver, the
stream simply plays at the level the device is already set to and volume stays with that provider.

A volume is still sent when the AirPlay output itself is the resolved volume control, and when a
mute has to travel with the stream. See
[grouping and volume](../../../docs/architecture/grouping-and-volume.md) for how a control is
resolved.

## Volume feedback and its echo

Devices report their own volume changes back, and those are applied unless the player is configured
to ignore them. Genuine Apple devices are set to ignore them automatically, because they manage
volume internally.

The problem is that a receiver **also echoes back every level it is handed**. An echo arriving after
the next level was sent would be read as the user reaching for the volume knob and written straight
back to the device, which is how a volume slider ends up fighting itself.

Reports are therefore ignored for a short window after the server sends a volume itself, and for the
whole span of an announcement, where two deliberate level changes happen in quick succession.

## Independent control planes

Devices with their own control plane keep streaming, control and playback monitoring on separate
connections, because they answer different questions and fail independently.

| Plane | Provides |
|---|---|
| Companion | Power state, wake, power control, native playback and volume, independent of streaming |
| Media remote tunnel | External playback monitoring: the active app, its metadata, elapsed time and transport state |

A sleeping device is explicitly woken before a stream is started or resumed.

What a given device offers varies. Apple TVs generally expose both. Current HomePod firmware
advertises a control plane without a PIN-pairing path, so power and wake control is unavailable
there, and it uses the transient monitoring tunnel with no PIN and nothing persisted.

**Third-party receivers stay protocol endpoints regardless of what they advertise**, which keeps
their exposed player id stable and their merging into one user-facing player intact. See
[protocol linking](../../../docs/architecture/protocol-linking.md).

## Related

- [streaming.md](streaming.md) for announcements, which drive volume twice in quick succession.
- [binaries.md](binaries.md) for the outbound command channel.
- [Players](../../../docs/architecture/players.md) for control chains and power.

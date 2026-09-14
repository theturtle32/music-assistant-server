# AirPlay

Streams audio to AirPlay devices: HomePods, Apple TVs, Macs, and the many third-party speakers and
receivers that speak one of the AirPlay protocols. Receiving AirPlay *into* the server is a
different provider, [airplay_receiver](../airplay_receiver/README.md).

It is the most intricate player provider in the tree, because AirPlay is really several protocols
with different timing models, and because precise multi-room synchronization is the whole point.

## Deep dives

- [Streaming and synchronization](streaming.md): the stream session, start timing, late join, and
  the shared clock.
- [The streaming binary](binaries.md): why the streaming runs in an external binary, and how it is
  driven.
- [Pairing, remote control and volume](control.md): pairing, remote control from the device, volume
  ownership, and the independent control planes on Apple devices.
- [The Sendspin bridge](sendspin-bridge.md): bridging AirPlay players into the native synchronized
  protocol for cross-protocol grouping.

## Module layout

| Module | Role |
|---|---|
| `provider.py` | Discovery, the remote-control server, the shared clock daemon, player construction |
| `player.py` | The player base and the generic protocol endpoint |
| `control_player.py` | The player model for devices with their own control plane |
| `stream_session.py` | One streaming session across a leader and its synchronized members |
| `stream.py` | One device's stream: the binary process, its feed, and its status |
| `pairing.py` | Both pairing flavours |
| `sendspin_bridge.py` | The bridge to the native synchronized protocol |
| `dashboard.py` | Casting a dashboard to an Apple TV |
| `helpers.py`, `constants.py` | Binary lookup, record serialization, tuning values |
| `bin/` | Where the streaming binary is placed; see [cliairplay binaries](bin/README.md) |

## Route selection is the binary's job

There is no protocol picker. The provider hands the binary the device's full advertisement and it
resolves the route from the advertised feature bits: legacy or modern protocol, native or
compatibility flow, transient or stored-credential pairing, and which clock to time against.

The server mirrors only the one test it needs for its own planning, namely whether a device
supports the modern protocol at all, since that decides which pairing flavour to run and which
service to target.

**The server never rewrites that choice.** When an automatic route conclusively fails, it logs a
warning pointing the user at the manual override and leaves the decision to them. A persisted
automatic switch would outlive the network dropout that usually caused the failure and pin the
player to a lane the device may not even accept.

The override is an advanced per-player setting, and the lanes it offers are filtered by what the
device actually advertises. Apple receivers are offered every lane except one, because they render
silence when timed that way, which was measured rather than assumed.

Hi-res playback is enabled automatically for receivers that advertise it. Both the realtime and
buffered format tables are consulted, because receivers understate them: at least one lists hi-res
for its buffered stream only while rendering it fine on the realtime one.

## Discovery and player identity

Four service types are subscribed. Two build the player, the primary service and the legacy one,
and two feed the independent control planes on Apple devices.

A player id derives from the device's hardware address. Instances of the server's own receiver
provider are skipped during discovery, so the server does not stream to itself.

## Two player models, decided once

| Model | Devices | Consequence |
|---|---|---|
| Standalone player | Apple TV, HomePod | Top-level player, never merged with other protocols, with its own control and monitoring planes |
| Protocol endpoint | Everything else | Merged into one user-facing player when the same device is also reachable another way |

**The model is decided from the device's own identity and never changes for a registered player.**
It determines the player id API consumers see, a protocol endpoint behind a parent versus a
standalone player, and that has to stay stable for Home Assistant and other clients. The identity
is present in the very record that creates the player, so unlike the separate control records it
cannot vary with discovery timing.

Which control features a standalone player then offers is decided from advertised capabilities and
degrades gracefully. See [Pairing, remote control and volume](control.md), and
[protocol linking](../../../docs/architecture/protocol-linking.md) for how endpoints merge.

## Configuration

Beyond the route override, the per-player settings worth knowing are a device password stored
encrypted and collected through the setup flow rather than a settings form, a switch to ignore the
device's own volume reports, a synchronization offset in milliseconds for a device that adds
latency downstream, and an override of how much audio the receiver keeps queued ahead of playback.

That last one is not cosmetic. Receivers whose internal pipeline starves at the shallow default
render nothing behind an otherwise healthy session, and deepening their queue is what makes them
play at all. It defaults per device family, applies to the modern route only, and its cost is
described under the limitation below.

Pairing credentials are stored per plane and separately from each other; see
[Pairing, remote control and volume](control.md).

## Limitations worth knowing

**Warm boundaries wait for the queued audio.** On the modern route, pause, seek and track change
leave the audio the receiver already holds in place, so it renders that first and the queue depth
is also the delay before the boundary is heard. Dropping the queue instead produced audible noise
bursts on real hardware, so keeping it is an accepted trade-off. It is most noticeable on pause,
where a user expects sound to stop at once, and on a receiver that needs a deep queue to render at
all it cannot be tuned away without silencing the device.

**Pausing a synchronized session parks the whole session** rather than pausing members
individually, so they resume sample-aligned. The park belongs to the session rather than the group,
so breaking up a paused group leaves the remaining player parked until a queue-driven re-anchor
revives it. A member that has lost its connection falls back to stopping.

**Remote control from the device only works while streaming.** Idle and external-playback control on
Apple devices goes through their own control planes instead.

**Explicit power and wake control is unavailable on HomePods**, whose current firmware does not
advertise a pairable control plane.

**Artwork reachable only through the image proxy does not render on an Apple TV** now-playing
screen, while externally hosted art does.

## Credits

The streaming binary builds on [libraop](https://github.com/music-assistant/libraop), with
[OwnTone](https://github.com/OwnTone) as the reference for the modern protocol and its pairing, and
[pyatv](https://github.com/postlund/pyatv) providing the Apple control and monitoring
implementations.

## Related architecture docs

- [Players](../../../docs/architecture/players.md) for the player model and command routing.
- [Protocol linking](../../../docs/architecture/protocol-linking.md) for how AirPlay endpoints merge
  into one device.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for the grouping models.
- [Playback](../../../docs/architecture/playback.md) for where this sits in the audio pipeline.
- [Discovery](../../../docs/architecture/discovery.md) for how these devices are found.

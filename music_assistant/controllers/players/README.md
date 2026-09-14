# Player controller

Manages every connected player: command routing, state resolution, protocol linking, grouping and
announcements.

## Deep dives

- [Protocol linking internals](protocol-linking.md): identifier matching, the linking flows, output
  selection, and the persisted state behind them.
- [Writing a player provider](authoring-a-player.md): what a player provider has to supply, and how
  to make protocol linking work for your devices.

## Module layout

The controller is assembled from mixins so each large concern lives in its own module.

| Module | Role |
|---|---|
| `controller.py` | Registration and lifecycle, command routing, availability, event signalling |
| `protocol_linking.py` | Matching protocol players to devices, wrapper creation, link lifecycle, output selection |
| `audio_sources.py` | The live external source sessions held per player |
| `announcements.py` | Interrupting playback to announce, and restoring afterwards |
| `helpers.py` | The command decorator, power waiting, and small shared types |

## Two objects per player

| Object | Is | Who touches it |
|---|---|---|
| `Player` | The live model a provider supplies, with the device's raw reported state and the control methods | A provider reports onto it; the controller commands it |
| `PlayerState` | The resolved snapshot, with user customizations and overrides applied | This is what the API exposes; clients see only this |

A provider never computes the values clients see. It reports what the **device** says, and the
framework layers the rest on top: user customizations such as a custom name or hidden status, and
the control chains that resolve power, volume and mute. A snapshot is produced whenever state is
updated.

That separation is the single most important thing to understand before writing a player provider.

## Player types

| Type | Is |
|---|---|
| Player | A device with native vendor support |
| Protocol | A generic streaming endpoint without native support, hidden from the UI and either wrapped or attached to a native player |
| Group | Synchronized playback across several speakers |
| Stereo pair | Two speakers acting as one |
| Display, Light, Source, Visualizer | Devices that take part in playback without being speakers |

The non-speaker types mainly affect presentation, in particular the default icon. Two of them are
excluded from group-target expansion, because neither is something audio can be grouped onto.

The distinction between the first two is about **who made the device**, not what it speaks. An
Apple speaker discovered over AirPlay is a native player; a third-party soundbar discovered over
the same protocol is a protocol player.

## Protocol-backed players

A player with no playback capability of its own, whose commands route to a linked protocol player,
should subclass the protocol-backed base rather than reimplement the delegation. It supplies
availability from the backing protocols, setup passthrough, delegated state and transport, and
surfacing of an external source playing on a linked protocol.

A subclass supplies only the list of protocol players backing it.

## Live audio sources

An external source playing on a player is held as a session per player, **independent of that
player's queue**. Selecting a Connect integration therefore leaves the queue untouched, and
questions about the live source are answered from the session rather than by inspecting a queue
item.

A source plays on one player at a time. The claim commits when a stream request is accepted, and
eviction of the previous holder happens only on the first request for a selection, so a takeover
that never streams leaves the source where it was.

Plugins push metadata and playback options through this mixin, and unloading a provider drops every
session belonging to it, because a live source cannot outlive the plugin exposing it.

## Announcements

An announcement accepts either a URL or a message to speak. A message is rendered up front through
a speech engine, so a group fan-out plays the resulting audio rather than every member re-speaking
the sentence.

The flow saves player state, interrupts, plays the clip with the pre-announce chime, and restores
what was there.

## Grouping

Grouping commands converge on one pipeline that validates and normalizes, then translates visible
player ids onto the protocol players actually carrying the audio. See
[grouping and volume](../../../docs/architecture/grouping-and-volume.md).

## Related architecture docs

- [Players](../../../docs/architecture/players.md) for the model and command routing.
- [Protocol linking](../../../docs/architecture/protocol-linking.md) for merging one device's
  protocols.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for groups and volume
  routing.
- [Playback](../../../docs/architecture/playback.md) for what happens after a play command.

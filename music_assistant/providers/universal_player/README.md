# Universal player

A wrapper player standing in front of the protocol endpoints of one physical device, for devices
with no native vendor support. An AV receiver reachable over three protocols appears as one player
with three selectable outputs instead of three players the user has to guess between.

These players are never created by hand. The player controller creates one when protocol endpoints
match the same device and nothing native claims it, and this provider only owns the player model.
The matching itself, and the linking flows around it, live in
[Protocol linking internals](../../controllers/players/protocol-linking.md).

## Module layout

| Module | Role |
|---|---|
| `provider.py` | The provider, holding the registered wrappers |
| `player.py` | The wrapper player: feature aggregation and state derivation |
| `constants.py` | The id prefix and config keys |

A builtin provider with no features of its own, since it supports no manual creation.

## It derives everything

A wrapper starts with no capabilities and takes them from its linked protocols: volume from
whichever protocol handles it best, power from any protocol that has it, transport from the active
one.

**It deliberately cannot play media itself.** Starting playback selects an output protocol and
routes there, which is what keeps one code path for "where does this player actually play" rather
than giving the wrapper a fourth answer.

Availability follows from whether any linked protocol is genuinely usable, meaning reachable **and**
not awaiting setup, and the wrapper forwards the *reason* rather than just the fact, so a user sees
"pairing required" on the player they can actually see.

## The id is minted once and never derived

A wrapper id is opaque and random, created when the device is first wrapped, carrying no device
information and never recomputed.

That is a correction of a real bug rather than a style choice. The player id is the identity API
consumers bind their entities to, so it has to be stable for the device's lifetime. Deriving it from
whatever identifiers happened to be available made it shift as the set of registered protocol
players changed, from a hardware-address-based id to a unique-id-based one, which orphaned the
consumer's entity.

A wrapper is therefore always resolved through the parent id each of its protocol players persists,
never by re-deriving one.

The consequence is a deliberate asymmetry in cleanup. A wrapper config is deleted only when the user
removes the player, when a native player takes the device over, or when it is absorbed into another
wrapper for the same device; the last two carry its settings across first. When its protocol players
merely disappear it becomes unavailable and **keeps its config**, because an opaque id cannot be
recreated from the device.

## Handover to a native provider

If a native provider is installed later, the controller hands the device over: every protocol link
is re-pointed, the user's configuration including name, values, processing and queue settings is
carried across, group memberships are re-pointed, and the wrapper is removed.

**The handover is not unconditional.** A protocol player may refuse the new link, most often because
the native player already holds an active link from that protocol domain. If anything stays behind,
the wrapper is **kept** and only the protocols that actually moved are handed over, so the refused
ones are not orphaned. Both players then coexist until a later evaluation resolves the rest.

## Configuration

Nothing is required. A user can rename the player, choose a preferred output protocol, disable it,
or remove it, which wipes its config and restarts protocol discovery from scratch.

## Related architecture docs

- [Protocol linking](../../../docs/architecture/protocol-linking.md) for why wrappers exist, how
  endpoints are matched, and how an output is chosen.
- [Players](../../../docs/architecture/players.md) for the player model and command routing.
- [Discovery](../../../docs/architecture/discovery.md) for how the endpoints are found.

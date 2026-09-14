# Sync group

Persistent groups of speakers that play in sync through their **own** protocol. A sync group is a
real player with its own queue and configuration, not a temporary arrangement between two speakers.

It never touches audio. It elects one member as the sync leader, forwards playback to it, and lets
that member's native protocol synchronize the rest. Cross-protocol grouping is a different provider,
[universal_player](../universal_player/README.md).

## Deep dives

- [lifecycle.md](lifecycle.md): forming, dissolving, the session signal, and optional power.
- [membership.md](membership.md): compatibility, adding and removing members, leader handoff.

## Module layout

| Module | Role |
|---|---|
| `provider.py` | Registering groups from config, and creating and removing them from the UI |
| `player.py` | The group player: leader election, state derivation, member commands |
| `constants.py` | Config keys, feature sets and timings |

It is a builtin provider, always present, single-instance and not disableable.

## Against ad-hoc sync

The distinction is worth holding, because both produce synchronized speakers.

| | Ad-hoc sync | Sync group |
|---|---|---|
| Exists when idle | No | Yes, as a player |
| Owns the queue | The leader does | The group does |
| Leader | Chosen by the user | Elected automatically |
| Survives a restart | No | Yes |

## The sync leader

The group does not play. One member is elected leader, receives the actual playback command, and
syncs the others to itself. Election happens when the group forms, and is re-evaluated when the
leader leaves or becomes unavailable.

Election prefers, in order: the current leader if it is still available; a member the **live session
already feeds**, since only such a member can inherit the session without a teardown; a member
supporting the currently active output protocol, so the group at least stays where it is; a member
from the configured list; and finally the first available member.

The leader is the source of truth for the group's state. Playback state, elapsed time, current media
and active source are all read from it, and it contributes the features below.

**The leader reads its own state, not the group's.** A leader mirroring its parent group would close
a cycle, group deriving from leader and leader deriving from group, leaving both stuck on their last
value. Members of an active group therefore report their own raw state; only manually synced
children mirror their leader.

Elapsed time is polled from the leader every second while playing and far less often when idle,
rather than forwarded. Forwarding every tick through the group's update chain would put a per-second
cascade on the event bus for no gain.

## Features are inherited

The group itself only ever guarantees that it can play media, plus a power toggle when the user has
assigned one and member changes when the group is dynamic.

Everything else, enqueueing, gapless playback, volume, mute and multi-device DSP, is inherited from
the active leader. While the group is dormant those are derived from the available configured
members instead, so a volume control is still advertised on a group nobody is playing to.

## Grouping runs through the leader's protocol linking

A leader may be a device reachable several ways. The playback command is forwarded to it, and **it**
picks its output protocol, preferring one already grouped or synced, then the user's preference,
then native playback, then the best remaining by priority.

That is what lets a group mix an AV receiver that speaks several protocols with speakers that speak
only one: the receiver selects the protocol its fellow members can actually join. See
[protocol linking](../../controllers/players/protocol-linking.md).

## Configuration

Group members is a multi-select of non-group players, permanent for a static group and initial for a
dynamic one. Dynamic members allows runtime changes, and lets a group start empty. Allowed members
optionally restricts who may join a dynamic group at runtime; empty means anyone compatible, and
preset members may always join.

## Related architecture docs

- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for the three grouping
  models and volume routing.
- [Players](../../../docs/architecture/players.md) for the player model these delegate through.
- [Protocol linking](../../../docs/architecture/protocol-linking.md) for output protocol selection.
- [Playback](../../../docs/architecture/playback.md) for how group audio is delivered.

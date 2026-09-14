# Membership and compatibility

Part of the [sync group provider](README.md). Who may join, and what happens when someone leaves
mid-session.

## Compatibility is enforced, not hoped for

Players can only be grouped when they share a sync protocol, and the group enforces that rather than
discovering it at playback time.

The first member's set of players it can group with becomes the reference. Later members must appear
in that set, and incompatible ones are skipped during formation.

**That set already includes the leader's linked output protocols**, which makes the rule less
restrictive than it first sounds. A speaker that only speaks AirPlay is a valid member for a Sonos
leader that also has AirPlay as a linked protocol, because the leader can move to the protocol they
share. See [protocol linking](../../controllers/players/protocol-linking.md).

## Static and dynamic

A static group has fixed membership, defined at creation, and all of its members rejoin
automatically when playback starts. It is the whole-home setup that should always be the same rooms.

A dynamic group advertises the ability to change members at runtime, can start with none, and
optionally restricts who may join.

## Adding a member

A candidate must exist, be available, and be permitted by the allowed-members list when one is
configured. Preset members are always permitted.

With no leader yet, meaning an empty or dormant group, the member is simply registered and sync
happens when the group is next formed.

Otherwise compatibility is checked against the current leader, and **an incompatible member is not
registered at all**. Registering it anyway would strand an orphan entry in the group that never
plays and that the user has to work out how to remove.

A compatible member is appended and forwarded to the leader, which handles protocol selection, and
may switch its own output protocol so the new member can join through one they share.

## Removing a member

A non-leader member is removed from the internal list and forwarded to the leader. Static members
cannot be removed. Removing the last member dissolves the group.

Removing the **leader** while playing is the interesting case, and it has two paths.

### Live handoff, where the protocol allows it

Some protocols support switching the leader of a live session without tearing it down. Where the
active protocol is one of them, a new leader is picked from the players the live session already
feeds, the old leader is removed from the session, and the remaining members are added to the new
leader's session. The remaining members keep playing.

### Dissolve and re-form, where it does not

Where the protocol cannot hand off, or where **no remaining member is part of the live session**,
the group dissolves and re-forms, which costs a brief audio gap.

The second condition is easy to miss and is the more common one. If the only members left are
freshly added players the session has never fed, there is nothing to hand the session to, whatever
the protocol supports.

## Related

- [lifecycle.md](lifecycle.md) for the debounced re-form a leader removal schedules.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for the set-members
  pipeline these commands arrive through.

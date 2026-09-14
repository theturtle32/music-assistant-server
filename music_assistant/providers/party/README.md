# Party

A plugin that lets guests at a gathering queue music from their own phones, without giving anyone
an account on the server.

It touches no audio of its own. What it contributes is a guest entry path, a set of scoped
commands, and a queue insertion policy that keeps guest requests from either being ignored or
trampling what is already playing.

## Playback host

Playback runs on a [shared playback session](../../helpers/shared-playback.md), venue or remote,
chosen once in config rather than per event. Venue plays out loud on a real speaker; remote plays
on each guest's own device.

## Guest access

Guest access is optional and off until enabled. When on, the plugin creates a single guest account
and issues a join code for it, and builds a join URL that guests reach by link or QR code. The URL
is a remote one when remote access is enabled and a LAN one otherwise.

Guest tokens are revoked when the plugin is removed **or** when guest access is switched off, read
from the live config rather than a snapshot taken at load, so turning the toggle off actually ends
the party rather than leaving valid tokens in circulation.

The entry mechanism itself, including why a join code can only ever be issued for a guest account,
is in [api and auth](../../../docs/architecture/api-and-auth.md).

## Queue insertion is a sectioning problem

Guests add tracks to a queue that is already playing and already has content. Appending would mean
a guest's request plays in an hour; inserting at the front would mean the last guest always wins.

So guest additions form a **priority section** after the current track, and boosted items form
their own sub-section at the front of that. New items land at the end of the matching section,
found by scanning forward for the most specific marker attribute, so ordering within a section is
first-come.

Two details in that are load-bearing.

**The boundary is the committed index, not the current index**, while the queue is playing. The
next track may already be buffered, and inserting before it would produce an item the player skips
straight past.

**One lock covers reading queue state, computing the insert index and loading the item**, so two
guests adding at the same moment cannot interleave and land on the same index. When the queue is
idle the same lock also covers resolving, inserting and starting playback, so two guests do not
both start it.

Optionally, duplicates are refused, which is what stops a room of people all adding the same song.

## Commands

The plugin registers its commands only when guest access is on, and each declares the scope it
needs rather than assuming guest. Reading the join URL, the host player and the config need read
scopes; adding, boosting and skipping need queue control; listening in needs player control. A
guest role holds exactly those control scopes and nothing that writes to the library or touches
configuration.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the plugin categories and the provider model.
- [API and auth](../../../docs/architecture/api-and-auth.md) for guest roles, join codes and scopes.
- [Playback](../../../docs/architecture/playback.md) for how the queue it writes into behaves.
- [Shared playback sessions](../../helpers/shared-playback.md) for the session abstraction.

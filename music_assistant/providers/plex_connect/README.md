# Plex Connect

Makes a Music Assistant player appear as a controllable device in the official Plex apps, so
Plexamp or the Plex web player can drive it.

It is **not** a receiver. No audio enters the server through it and it exposes no audio source.
Commands flow in from Plex and are translated into ordinary player and queue commands, which makes
it an external control bridge. Classifying it by its name would put it in the wrong category and
send a reader looking for stream handling that does not exist.

It depends on the Plex music provider, since the items Plex asks it to play have to resolve to
something the library can stream.

## One instance per player

Each instance links exactly one player and binds its own port, selected from a range at load time
and checked for availability first. Exposing several players means several instances, which is why
this provider allows them.

Discovery uses Plex's own broadcast protocol rather than mDNS or SSDP: the instance advertises
itself on the local network and answers searches, so the Plex apps find it the same way they find
any other Plex player.

## Module layout

The split follows the protocol surfaces rather than layers, because each one has its own wire
format and its own failure modes.

| Module | Handles |
|---|---|
| `gdm.py` | Broadcast advertising and answering searches |
| `server.py` | The remote-control HTTP surface Plex calls into |
| `timeline.py` | Reporting playback state back to Plex |
| `queue_sync.py` | Background queue loading and keeping the server's queue in step with Plex |
| `queue_commands.py` | The play-queue commands: play media, create and refresh a queue |
| `playback.py`, `parsing.py` | Playback actions and the Plex payload parsing they need |

Plex models playback as a play queue owned by the Plex server, while Music Assistant models it as a
queue owned by a player. Two of those modules exist entirely to keep those two ideas reconciled in
both directions.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the plugin categories, including why this is
  a bridge rather than a receiver.
- [Providers](../../../docs/architecture/providers.md) for dependencies and the load lifecycle.
- [Playback](../../../docs/architecture/playback.md) for the queue model it reconciles against.

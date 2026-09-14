# Plugins

A plugin is a provider that is neither a music source, a speaker, a metadata source nor an
analyzer. In practice that covers a lot: audio coming *into* the server, scrobblers reporting
plays outward, bridges advertising players on foreign protocols, and extensions that mount whole
new surfaces.

Every method on the plugin base class is optional, and feature-gated methods follow one pattern: a
plugin that declares a feature but does not implement it fails loudly, while a plugin that never
declares it gets a harmless empty result.

## Categories

| Category | Does |
|---|---|
| Receiver | Exposes live audio sources; audio flows into the server from an external app or device |
| Scrobbler | Receives playback reports and reports plays outward. Touches no audio |
| External control bridge | Advertises this server's players on a foreign protocol and translates inbound commands |
| AI and speech backend | Answers the query and speech provider features by exposing selectable engines |
| Guest and social | Guest access, join codes, shared playback sessions |
| Library and discovery | Implements music features such as browse, search or recommendations from a plugin |
| Server extension | Mounts a new server surface, virtual players, or diagnostics |

Only the first category touches the audio source machinery. The rest use the plain provider surface
plus whatever commands, event subscriptions or routes they register.

Classification is worth checking rather than guessing from a name: several things that look like
plugins are music or player providers, and at least one bridge declares no features and never
touches audio despite appearing in a player list.

Each in-tree plugin has a README beside it covering what it actually does; the table in the
[architecture index](README.md) lists them.

## Audio sources

An audio source is a **media item**, not a special case. It subclasses the media item model, so it
inherits an id, a provider, a name, metadata and a computed URI, which is exactly what makes it
addressable by browse, by URI resolution and by the ordinary play path.

It behaves like a live item similar to a radio station: enqueued as a single item, streamed
continuously, with metadata pushed by the owning plugin.

There are two id conventions, reflecting two bindings. **One source per provider instance** uses a
fixed id, so the instance id distinguishes two receivers of the same kind. **One source per player**
uses the player id, which is what lets a user enable a Connect integration on some speakers and not
others without configuring several provider instances.

Because an id is only provider-scoped, anywhere a server-wide unique value is needed uses the URI
instead. That distinction causes real bugs when ignored.

A provider may expose several sources, and the source list is re-read rather than cached, so the
set can change over the provider's lifetime.

### Capability flags are routing gates, not hints

Whether a source can pause, seek or skip is checked **before** a command is proxied, so a command
against a source that declares it cannot pause is silently not forwarded.

Two flags describe who may start a source, and they are genuinely independent: whether the server
may initiate it from the UI, and whether an external app may start it by picking this server as its
device. Only the first is enforced by core, through the browse filter; the second is a provider
contract.

A source that cannot be initiated is not a soft hint either. Its provider is expected to raise when
it cannot acquire the upstream producer, which is what receivers do when no external session is
connected.

Two further flags are documentation rather than gates: exclusivity and external triggering are
conventions the in-tree receivers implement themselves, and no controller reads them.

## Selection and ownership

A source plays for one consumer at a time, and the claim lives **inside the provider** rather than
on a central object. Every in-tree receiver implements the same pattern: record who owns it and the
session token that came with the request, and clear both only when the token still matches.

The streams controller owns the lifecycle, from two entry points that must stay in sync: the HTTP
route for players that fetch streams, and the direct-PCM path for providers that consume audio in
process. Both pair selection with release in a way that runs however the stream ended, including a
client disconnect or an exception.

Selection fires **before** stream details are requested, so a plugin can acquire its upstream
producer before being asked to describe the stream.

## What receivers have in common

Each receiver wraps a different protocol, but the recurring problems are the same, and they are
worth knowing before writing one.

**Volume is bidirectional and will ping-pong.** A level sent outward comes back as an echo. The
in-tree receivers deduplicate on the last value sent, recording it *before* awaiting the outward
call because the echo can arrive while the await is still in flight, and restoring the previous
value on failure so a retry is not wrongly suppressed.

**The first volume event of a session is usually the daemon's own default**, not the user's intent,
so it is ignored or grace-perioded to stop it clobbering the player's current volume.

**Pausing is not always a stream end.** At least one backend keeps its pipe open while paused and
simply stops writing, so the read side has to recognize a gap plus a not-playing state as a pause
rather than an end of stream.

**Formats are frozen at session start**, so a provider reload mid-session takes effect on the next
session rather than causing a sample-rate mismatch mid-stream.

**Targeting caches the queue rather than the player**, because some protocol players are ephemeral
bridges whose id stops being valid once torn down.

**"The player" is several players.** The one a source was selected on, the one actually consuming
the stream, which may be a protocol player or a sync leader, and the one a new session should land
on are routinely different. Releasing a source has to name the first and stopping playback the
second; getting that backwards leaves a source claimed forever or tears down a group that should
only pause.

Not every receiver has every one of those problems, and the exceptions are instructive. One never
sends volume outward, so it has no echo to suppress. One is fed by a passive protocol with no
session on the far side, so it never stops a previous player. One fetches its own audio rather than
having any pushed to it, so its capabilities change with whether a companion provider is loaded.

## Guests listening together

Two plugins host a group listening experience, and they share one abstraction for it: a session
wrapping a player that owns the queue, either a real speaker playing out loud or a hidden virtual
player that every guest's own device attaches to.

The part worth knowing is that a guest joining is a **grouping operation, not a second stream**, so
all the protocol translation in [grouping and volume](grouping-and-volume.md) applies unchanged.
See [Shared playback sessions](../../music_assistant/helpers/shared-playback.md).

Guest accounts and join codes are a separate mechanism; see
[The API and authentication](api-and-auth.md).

## Scrobblers

Scrobblers touch no audio. The server hands every playback report to the plugins declaring the
scrobble feature, through a plugin hook, rather than each of them subscribing to the event bus and
filtering on its own.

The hook fires for every queue, periodically while an item plays and whenever playback state or
the current item changes, so it also fires on pause, at the end and on a skip. Flags on the report
tell those apart. It can fire before the plugin has finished loading, so a plugin ignores reports
until it is ready. The report names the playing user and the player, so a plugin recording for only
some of them filters on those.

A shared helper builds the usual now-playing and scrobble handling on top of that hook, and its
decision-making is more than it looks. It filters by media type, by user and by player, so a
household can scrobble only certain users or rooms. It refuses a repeat of the last scrobble and
requires a full play, while reading a not-fully-played report for the same item as a restart, which
is what keeps a song on loop scrobbling.

Error containment is explicit: each subclass names its client library's error hierarchy, and those
errors are logged and swallowed, because a network blip must not break the event bus. Anything
outside that set surfaces as the bug it is.

## Related

- [Providers](providers.md) for the provider lifecycle and features.
- [Players](players.md) for live source sessions on a player.
- [Playback](playback.md) for how live audio bypasses the pipeline.
- [AI and MCP](ai-and-mcp.md) for the AI-facing plugins.
- [providers/vban_receiver](../../music_assistant/providers/vban_receiver/README.md) for the
  simplest receiver, and
  [providers/spotify_connect](../../music_assistant/providers/spotify_connect/README.md) and
  [providers/airplay_receiver](../../music_assistant/providers/airplay_receiver/README.md) for two
  that wrap an external daemon.
- [providers/plex_connect](../../music_assistant/providers/plex_connect/README.md) and
  [providers/yandex_smarthome](../../music_assistant/providers/yandex_smarthome/README.md) for
  bridges that carry commands rather than audio.
- [providers/radio_playlist](../../music_assistant/providers/radio_playlist/README.md) and
  [providers/sonic_similarity](../../music_assistant/providers/sonic_similarity/README.md) for
  plugins that implement music features.

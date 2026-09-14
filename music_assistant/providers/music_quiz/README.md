# Music Quiz

A multiplayer quiz engine. Guests join by QR code through the standard guest-access flow and play
on their own devices. It declares no provider features.

## Quiz types

Each type is a strategy class, and availability is decided per class rather than globally.

| Type | Answers | AI |
|---|---|---|
| Guess the song | Multiple choice | Optional, for ranking and inventing distractors |
| Music timeline | A shared chronological timeline, with optional artist and title bonuses | None |
| Trivia | AI-worded multiple choice, grounded in library metadata | Required |

The listing filters on each type's own availability check, and the trivia type reports itself
unavailable when no AI plugin is loaded. **It therefore does not appear as an option rather than
failing when selected.** The same check shapes configuration: the AI distractors setting is marked
read-only with an explanatory alert when no AI provider is present.

Playback is hosted by a shared playback session in either venue or remote mode, chosen per game.

## Guest-safe state by construction

Game state reaches clients as provider events scoped to this provider's instance.

The public state is guest-safe **by construction rather than by filtering at the edge**. Private
player ids never enter a broadcast at all. During an answering round the correct option, the
current song, the correct timeline placement and the bonus answers are all withheld, and the bonus
definitions are sent redacted. Only at reveal do the answer, the track, its artwork and the
per-player results appear.

A guest registers through a join command that returns a private player id, and that id then acts as
the credential for answering, readiness, heartbeats and state reads.

Deadlines are broadcast as authoritative server timestamps rather than as client-side countdowns,
so every device agrees on when a round ends.

## Three scope tiers

The command surface mirrors the trust model. Host commands, meaning create, start, reveal, advance,
reset and delete, require the invite scope. Participant commands are open to any authenticated
user, since a guest holds only a guest token. Listen-in commands require player control, because
they group a real player.

## Related architecture docs

- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for the AI provider-feature contract.
- [Plugins](../../../docs/architecture/plugins.md) for shared playback sessions.
- [API and auth](../../../docs/architecture/api-and-auth.md) for guest access and join codes.

# AI Radio

Takes a source playlist, decides where a human radio host would say something, generates that
speech, and interleaves the resulting audio with the music.

It declares **no provider features at all**. Almost everything it does, it does by calling other
subsystems, which makes it the clearest worked example of the AI provider-feature pattern; see
[ai and mcp](../../../docs/architecture/ai-and-mcp.md). The one thing it owns itself is clip
streaming, because a just-in-time render has to be served from somewhere.

## Deep dives

- [generation.md](generation.md): slots, the section rule DSL, and how speech reaches the queue.

## Module layout

| Module | Role |
|---|---|
| `provider.py` | The server-facing surface: command registration, engine selection, lifecycle |
| `runtime.py` | Section planning, generation, and both run modes |
| `rendering.py` | Just-in-time clip rendering and the stream details for serving it |
| `hosts.py` | Host personality storage and normalization, plus built-in presets |
| `queue_dj.py` | The sticky per-queue DJ |
| `storage.py` | Station and section persistence and normalization |

## Three concepts

Configuration is provider-local JSON, in two files with two API surfaces.

| Concept | Is |
|---|---|
| Station | A complete program: source playlist, target playlist or player, host instructions, which sections to use and the rules for placing them |
| Section | A reusable segment definition: a prompt, a character budget, a web-search mode. Shared across stations |
| Host | A named personality, meaning voice, tone and per-host speech options, that a station references. Ships with presets so a user need not write one |

Stations may embed section definitions inline, and saving lifts those into the shared store. Both
saving and validating run against a **scratch copy** of the section store, so a station that fails
normalization cannot leave half-applied section edits behind. A shared section cannot be deleted
while a station references it, and the error names the stations that do.

Queue DJ is a different entry point altogether. Rather than running a whole station program, it
attaches a sticky DJ to one queue that comments on whatever that queue happens to play, keyed by
session so it survives track changes.

## Run modes

**Playlist mode** builds a whole playlist. Against the builtin provider it composes rich entries
with cover art and resolved durations and imports them directly. Against any other playlist
provider it composes a plain URI list, creates the playlist, and adds the tracks through the normal
background task.

**Dynamic mode** feeds a live queue in batches. Each batch plans, generates, synthesizes and
enqueues a configurable number of tracks plus their sections, with a one-track lookahead so a
between-songs segment can reference a track that has not been queued yet. The loop then waits until
playback approaches the end of the batch before generating the next one.

The first batch replaces the queue when the station asks for that and otherwise appends, and
because appending does not start an idle queue, an explicit play follows.

The wait loop's stall detection is careful about what counts as progress. Its inactivity deadline
resets when the index advances, when the queue is paused, which is a deliberate user action rather
than a stall, and when elapsed time moves at all. A long track or a paused player therefore does
not abort a run, while a genuinely stuck queue does, with an error naming the last index seen.

Concurrency is capped, and a station can have only one active run. Both guards and the session
insert live inside a single critical section, because an await between the check and the insert
would let concurrent callers slip past. Finished sessions are retained and pruned to the newest
few.

## Dynamic mode is unrelated to dynamic playlists

Despite the name, this provider's dynamic mode has **nothing to do with dynamic playlists**. It
never sets the dynamic flag, never registers a managed pool, and never takes part in the bounded
pool refill machinery.

It is a plugin-side loop that enqueues on a schedule of its own. The two mechanisms can coexist on
a queue but do not cooperate. A station's source playlist may be a dynamic playlist only in the
sense that any playlist URI works as a source.

## Related architecture docs

- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for the provider-feature contract this consumes.
- [Playback](../../../docs/architecture/playback.md) for how enqueued items reach a speaker.
- [Plugins](../../../docs/architecture/plugins.md) for the plugin provider model.

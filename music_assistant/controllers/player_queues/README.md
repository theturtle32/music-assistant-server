# Player queues controller

Turns "play this" requests into actual playback. Each player owns one queue, holding that player's
items and playback state. The controller accepts and applies enqueue requests, drives transport,
and keeps the in-memory queue state reconciled with what the player actually reports.

A player's queue is normally its active source, but a player can also play something else, such as
an external or native source. The coupling is deliberately loose: the queue is the usual active
source, not the only possible one.

## Deep dives

- [state.md](state.md): the server record, persistence, reconciling against the player, play counting.
- [continuation.md](continuation.md): look-ahead and buffering, the managed pool, autoplay, ordering.

## Module layout

| Module | Role |
|---|---|
| `controller.py` | The public face: in-memory state, config entries, API commands, inter-controller event hooks, and the core load, signal and persistence primitives |
| `base.py` | The shared base the three logic mixins extend, declaring the per-queue state and core operation signatures so each mixin type-checks on its own |
| `queue_loader.py` | Applies the enqueue option, loads items, resumes from the playlog, and runs the dynamic and autoplay refills |
| `playback_tracker.py` | Reconciles queue state from player updates, handles end of queue, and counts plays |
| `stream_feeder.py` | Enqueues the next item on the player, prepares its audio buffer, and cleans up stale buffers |
| `state.py` | `PlayerQueueData`, the complete server-side per-queue record, and the cache serialization |
| `media_resolver.py` | Resolves source media into the concrete tracks to enqueue, and resolves an item's successor |
| `autoplay.py` | Resolves the per-queue autoplay mode and produces the next batch for the library and playlist modes |
| `managed_pool.py` | The bounded dynamic-source pool, topped up and recency-gated |
| `smart_shuffle.py` | Recency-aware, well-spaced ordering of the upcoming items |
| `smart_fade_ordering.py` | Transition ordering from stored analysis only, shared by both queue modes |
| `config.py` | The core-module and per-queue config entry schemas |
| `constants.py` | Config keys, defaults, and the two cache category identifiers |
| `helpers.py` | Stateless utilities: the previous-state snapshot, the playback-lock decorator, and pure helpers |
| `strings.json` | Translatable name and description of the core module |

The stateful helpers stay composition objects, each constructed with the controller and reaching
back through it. The stateless logic lives on mixins so it operates on the controller's own
per-queue state directly. `helpers.py` never imports the controller at all: its play-action
decorator types the host through a local protocol, which is what keeps the import cycle out.

## The wire snapshot and the server record

Two objects per queue, and the distinction is central.

`PlayerQueue`, from the shared models package, is the client-facing snapshot: playback state,
shuffle, repeat, crossfade and autoplay flags, flow mode, the sources as item mappings, the current
item and index, and elapsed time. It holds no server-only state.

`PlayerQueueData` is the complete server-held record, one per queue. It wraps the wire snapshot and
adds everything that never leaves the server: the ordered item list, the full media items behind
the dynamic sources, the enqueued parent items, the owning user, the transient stream-session
fields, and runtime bookkeeping. It owns the serialization for both. This mirrors how the player
controller pairs runtime state with the wire player model.

## Invariants

**A queue id is a player id.** Every queue belongs to a leaf player, a group player or a sync
leader, and the shared id is what keys the per-queue records and the cache entries, so a transport
command keyed on a queue id reaches the right player.

**One queue object per player, but reconciliation is gated by type.** A queue object is created for
every player on register and removed on player remove. Protocol players are never reconciled, so a
protocol player's queue object stays inert.

**Active means active source.** A queue is active only when the player's active source is this
queue or nothing. An inactive queue with no prior state is forced idle.

**Transitioning queues are skipped.** While a queue is marked as transitioning, incoming player
updates for it are ignored, which keeps mid-track-change reconciliation glitches out.

**Media time is not stream time.** The queue stores elapsed time in media time, so it is usable
directly as a resume position, while the player reports stream time after the tempo filter. The two
are bridged by scaling with the current item's playback speed.

**A replace swaps the contents and never empties the queue first.** The queue keeps playing what it
has while the new media is resolved, which takes one or more provider round-trips, and the items are
exchanged in one update, so clients never observe an empty queue with nothing playing. The dynamic
path rebuilds its pool from the start for a replace rather than behind the playing track, which is
what play wants, and holds reconciliation off while it does, because the pool is fetched with the
queue already truncated. The outgoing audio is released before the swap, while those items are still
on the queue. Afterwards nothing reaches them, and the track being started needs the source slot
they hold.

**Shuffle is a queue setting, and only the media's own order overrides it.** Shuffle stays as the
user left it across everything they play, except when the media carries an order of its own.
Starting an album, podcast, episode, audiobook or audio source with play or replace switches
shuffle off, because those are sequenced content rather than a pool of tracks. An explicit argument
always wins, and the first item of a batch decides for the whole batch, since it is the only media
type known before the items are resolved. Switching shuffle off restores the remaining items to
their original order rather than leaving them shuffled behind a queue that now reads unshuffled. The
options that only stage items for later leave shuffle alone. A dynamic queue is exempt and forces
shuffle on, because it is an always-on smart mix.

## Concurrency

Transport and playback actions on a queue are serialized through the player's shared playback lock,
which is re-entrant, so nested actions on the same queue do not deadlock. While an action is in
progress a flag is surfaced on the queue and reported to subscribers.

Background and delayed work, meaning next-item preloading, buffer preparation, radio fill,
resume-on-idle and delayed clear or resume, is dispatched as tasks or timers rather than run inline.
Those are cancelled on player removal and on stop, so stale work cannot enqueue after a queue has
stopped. Long passes such as a full shuffle yield to the event loop while running.

## Configuration

As a core module the controller exposes config entries for default enqueue behaviour in three
groups. Per-media-type default enqueue options decide whether playing that type plays or replaces.
Selection modes decide how artists and albums expand into tracks. Click actions decide what a
client does when an item is clicked.

The click actions are not read by the server at all. They live here so every client resolves the
same behaviour from one discoverable, translated schema instead of each defining its own local
preferences.

Per-queue entries cover autoplay, crossfade and volume normalization. Each is a tri-state that
falls back to the global value on this core module, so a queue only overrides what the user changed.
See [controllers/config](../config/README.md).

## Related architecture docs

- [Playback](../../../docs/architecture/playback.md) for the end-to-end flow from a play request to audio on a speaker.
- [Players](../../../docs/architecture/players.md) for command routing and the playback lock.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for which player a group's queue belongs to.
- [Plugins](../../../docs/architecture/plugins.md) for audio sources and dynamic playlists.

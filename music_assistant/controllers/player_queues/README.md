# Player queues controller

Turns "play this" requests into actual playback. Each player owns one queue, holding that player's
items and playback state. The controller accepts and applies enqueue requests, drives transport,
and keeps the in-memory queue state reconciled with what the player actually reports.

A player's queue is normally its active source, but a player can also play something else, such as
an external or native source. The coupling is deliberately loose: the queue is the usual active
source, not the only possible one.

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

## State and persistence

All live state is in memory, one record per queue. Durable state goes to the cache controller under
two categories, queue state and queue items, keyed by queue id. The state entry is a versioned
envelope, so an incompatible format is discarded rather than misread.

Writes are debounced, marked persistent, and issued per category only when that category's content
actually changed. Volatile progress fields such as elapsed time do not count as a change, so
neither category is re-serialized on every state tick.

Restore is deliberately resilient. A queue's settings survive even when some of its media items no
longer deserialize. On registration both entries are restored, the dynamic-source flag is
recomputed, and the play-action flag is reset in case the server was killed mid-action. Permanent
player removal drops the record and both cache entries.

## Concurrency

Transport and playback actions on a queue are serialized through the player's shared playback lock,
which is re-entrant, so nested actions on the same queue do not deadlock. While an action is in
progress a flag is surfaced on the queue and reported to subscribers.

Background and delayed work, meaning next-item preloading, buffer preparation, radio fill,
resume-on-idle and delayed clear or resume, is dispatched as tasks or timers rather than run inline.
Those are cancelled on player removal and on stop, so stale work cannot enqueue after a queue has
stopped. Long passes such as a full shuffle yield to the event loop while running.

## Reconciling against the player

The controller consumes player lifecycle and per-update callbacks. From what the player reports it
decides whether the queue is active, derives the current index and item, and recomputes elapsed
time. It diffs the incoming state against the previous snapshot to detect transitions, such as a
track played to completion or the end of the queue, and emits queue and time events.

Flow mode is the special case. Instead of one stream per track the whole queue is a single
continuous stream of concatenated items, so the player's cumulative index and position have to be
mapped back to a per-track index and per-track elapsed time.

## Look-ahead and buffering

For gapless playback and crossfades the controller anticipates the upcoming item: it computes the
next index, pre-resolves that item's stream details, and hands the next item to the player ahead of
time. Warming the next track's audio buffer is not part of this path. The streams controller
triggers it near the end of the current track through a callback into this controller.

Every buffer records the session that claimed it. A stop leaves alone only what the session playing
now claimed, so playback that restarted before the stop got that far keeps its audio. Everything
else goes, including what earlier sessions left behind, because sessions rotate without a stop and a
claim that is no longer current marks audio nobody will come back for. A clear or a replace drops
the items themselves, so their audio goes with them.

## Keeping a queue going

Two refill paths share the same "running low" trigger.

A queue with **dynamic sources** is kept as a small bounded managed pool. Each source contributes
candidates by its fill mode: a dynamic playlist yields its own self-managing batch, while a finite
item mixed into the pool rotates its own unplayed tracks. Each top-up apportions slots across the
sources by weight, recency-gates every candidate, prefers the least recently played, nudges
recently heard artists back, and then best-effort spaces the assembled batch so adjacent tracks
avoid sharing an artist, seam-aware against the current tail. A radio is just a dynamic playlist
from the radio playlist provider.

**Autoplay** is the single "keep going" switch, and what it appends is dispatched on the media type
of the queue's last item, because that is the item the appended ones follow. Music continues with
the per-queue configured mode: similar tracks seeded from the enqueued items, an infinite
genre-biased library mix, a chosen playlist, or an automatic mode that tries similar first and falls
back to the library mix. A podcast episode or audiobook instead continues with its own successor,
the next episode or the next book in the collection, and simply ends the queue when there is none.
Live sources have no natural end, so autoplay does not apply to them at all.

Repeat masks the effective autoplay flag off while it is on. The queue keeps its saved preference,
either a pinned per-queue override or the current global default, so turning repeat off restores
that preference instead of changing it. Already-queued items stay put; only future autoplay
additions are blocked, and dynamic mode keeps its own refill behaviour.

## Ordering with smart fades analysis

When the option is on and smart crossfade is active, ordering can use the analysis smart fades
already has to improve the order of upcoming tracks. Recency stays in charge and no new tracks are
selected.

In normal mode the current and buffered part of the queue is left alone and only the future part
already considered safe to move is reordered, with the last fixed track as the starting point.
Within each recency tier the full movable population can be considered.

In dynamic mode the managed pool still picks the refill tracks, and ordering then sorts that
accepted batch from the existing queue tail. Both modes consider every remaining track in the run
being ordered; dynamic mode simply orders one refill batch at a time.

No analysis is started for this. Unknown data stays neutral. The score uses tempo, graded Camelot
key affinity and end-to-start energy, and those are ranking signals rather than filters. A silent
outgoing tail is ignored for the energy part. Close choices keep some randomness, and smart fades
still decides the actual transition.

## Resolving media into items

Non-track media has to be expanded into the tracks or episodes to enqueue. Each source type
resolves into a concrete track list, applying the configured selection rules, resolving library
versus provider variants, and optionally ordering the result. The same concern builds the playback
payload handed to the player, using the metadata controller for images.

## Play counting and resume

The controller decides when a track counts as played and reports it to the music controller. Plays
are deduplicated through a last-counted marker, with album-level handling, so a track is not
double-counted on the end-of-queue idle transition. It also computes and applies resume positions
for audiobooks and podcast episodes, and can restore a previously playing queue from the playlog.

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
- [Player control](../../../docs/architecture/player-control.md) for command routing and the playback lock.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for which player a group's queue belongs to.
- [Plugins](../../../docs/architecture/plugins.md) for audio sources and dynamic playlists.

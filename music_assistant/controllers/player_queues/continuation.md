# Look-ahead and keeping a queue going

Part of the [player queues controller](README.md).

## Look-ahead and buffering

For gapless playback and crossfades the controller anticipates the upcoming item: it computes the
next index, pre-resolves that item's stream details, and hands the next item to the player ahead of
time.

Warming the next track's audio buffer is not part of this path. The streams controller triggers it
near the end of the current track through a callback into this controller. See
[streams/buffering.md](../streams/buffering.md).

Every buffer records the session that claimed it. A stop leaves alone only what the session playing
now claimed, so playback that restarted before the stop got that far keeps its audio. Everything
else goes, including what earlier sessions left behind, because sessions rotate without a stop and
a claim that is no longer current marks audio nobody will come back for. A clear or a replace drops
the items themselves, so their audio goes with them.

## Keeping a queue going

Two refill paths share the same "running low" trigger.

### Dynamic sources and the managed pool

A queue with dynamic sources is kept as a small bounded pool. Each source contributes candidates by
its fill mode: a dynamic playlist yields its own self-managing batch, while a finite item mixed
into the pool rotates its own unplayed tracks.

Each top-up apportions slots across the sources by weight, recency-gates every candidate, prefers
the least recently played, nudges recently heard artists back, and then best-effort spaces the
assembled batch so adjacent tracks avoid sharing an artist, seam-aware against the current tail.

A radio is just a dynamic playlist from the radio playlist provider.

### Autoplay

Autoplay is the single "keep going" switch, and what it appends is dispatched on the media type of
the queue's last item, because that is the item the appended ones follow.

| Last item | Continues with |
|---|---|
| Music | The per-queue mode: similar tracks seeded from the enqueued items, a genre-biased library mix, a chosen playlist, or automatic, which tries similar first and falls back to the mix |
| Podcast episode | The next episode of that podcast |
| Audiobook | The next book in the collection |
| Live source | Nothing; a live source has no natural end, so autoplay does not apply |

Where there is no successor, the queue simply ends.

Repeat masks the effective autoplay flag off while it is on. The queue keeps its saved preference,
either a pinned per-queue override or the current global default, so turning repeat off restores
that preference instead of quietly changing it. Already-queued items stay put; only future autoplay
additions are blocked, and dynamic mode keeps its own refill behaviour.

## Ordering with smart fades analysis

When the option is on and smart crossfade is active, ordering can use the analysis smart fades
already has to improve the order of upcoming tracks. Recency stays in charge and no new tracks are
selected.

In normal mode the current and buffered part of the queue is left alone, and only the future part
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

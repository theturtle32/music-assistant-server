# Library sync

Part of the [music controller](README.md).

Sync keeps the local database in step with each provider's catalog.

## Scheduling

Loading a provider registers a recurring task per supported media type, each gated on that
provider's sync toggle for the type, and unloading unregisters them. The interval is per provider,
defaulting to twice a day. An on-demand sync runs the same tasks at higher priority and records the
requesting user.

A global lock serializes all provider syncs, so only one provider and media type combination runs
at a time. That avoids database contention and duplicate matching while several providers are
filling in the same items.

When the last sync task finishes, a completion event fires and the database cleanup task is queued.

## Writing in bulk

Two behaviours make a full sync affordable.

Each per-item block commits once rather than once per statement, so an item and all its relations
land together. Note that this batching is not a transaction: it always commits on exit, including
on error, because the connection is shared and rolling back would discard other tasks'
acknowledged writes.

The whole run suppresses per-item added and updated events. A library sync would otherwise emit one
event per touched item, serialized once per connected client. Clients follow progress through task
events and refresh once when the sync completes. Deletions are never suppressed.

Change detection avoids hydrating objects at all. A lightweight snapshot of ids, flags and raw
provider mappings is enough to decide whether a write is needed, so an unchanged item costs a
comparison rather than a full parse.

## Matching during sync

Items resolve by provider mapping, matching on the instance first and then on the domain. A hit
updates the row when it changed. A miss goes through the full match-and-store flow described in
[Matching and merging](media/matching.md), with the incoming mappings marked as in the provider's
library.

## Deletions

Deletion handling runs only when the provider has it enabled, and compares this run's ids against
the previous run's, cached per provider instance.

For a non-streaming provider with no other in-library mappings left, the item is genuinely gone and
is removed outright. Dangling rows would otherwise stay visible in artist and album views, which do
not filter on library membership.

Otherwise the mapping is kept and flagged as no longer in the provider's library. That preserves
the metadata accumulated against the item, and the item loses its favorite flag once no provider
has it any more.

## Removing a provider

Provider removal is a separate path from deletion. It walks the sub-controllers bottom up, making
a second pass over tracks, albums and artists to break relations, strips that instance's mappings,
and deletes its playlog rows.

The instance stays recorded in a hidden config value until the cleanup completes without errors, so
a removal interrupted by a restart resumes on the next startup rather than leaving the library
half-stripped.

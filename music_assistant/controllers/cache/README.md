# Cache controller

A centralized caching layer backed by SQLite. Everything stored here goes through JSON
serialization, so a value reads back the same way regardless of when or how it was written.

## Package layout

- `controller.py`: the `CacheController`, its read and write operations, and the database lifecycle.
- `constants.py`: shared constants and the bypass context variable.
- `helpers.py`: the `use_cache` decorator for provider and controller methods.

## Responsibilities

- Store and retrieve JSON-serializable data, namespaced by category, provider and key.
- Reject anything that is not serializable at write time rather than at read time.
- Support expiration, checksums, and entries that survive a cache clear.
- Reconstruct model objects on read when the caller names a base class.
- Cache provider and controller method results through a decorator.
- Serve bulk reads for callers that would otherwise check a large number of keys one at a time.
- Clean up expired entries on a schedule.

## Design notes

There is no in-memory tier. An earlier layered cache returned native Python objects from memory
and deserialized dictionaries from the database, and that inconsistency was worth more than the
speed. SQLite in WAL mode with memory-mapped I/O, a sizeable page cache and relaxed synchronous
writes is fast enough for every hot path. The mmap ceiling and page cache are not fixed values:
[helpers/database.py](../../helpers/database.py)
scales both to the host's total RAM, so a memory-constrained device gets a small footprint while a
large host keeps a big library hot.

Because everything round-trips through JSON, callers convert model objects to dictionaries before
storing them, and back afterwards. Both the controller and the decorator accept a base class so
the reconstruction happens for you.

Two flags control lifetime, and they are independent of each other. A persistent entry survives an
explicit clear unless the caller asks to include persistent entries. An entry flagged for stale
reuse survives the daily cleanup after it expires, so it stays available as fallback data. Those
rows are dropped once they are far enough past expiry that nothing is asking for the key anymore.

### Shared fetches and stale-while-revalidate

On a miss, the decorator shares one execution of the wrapped method between concurrent callers on
the same key, so a burst of identical requests costs a single provider call. Each caller gets its
own copy of the result, because callers do adjust results in place, per-user podcast resume state
being one case. The objects the fetch produced stay behind with the shared fetch, so the stored
entry is written from data no caller has touched. A result that cannot be copied is shared
instead, with a warning.

Opting a method into stale-while-revalidate makes an expired hit return immediately and schedule a
background refresh, deduplicated by key. A slow or briefly unreachable upstream then costs one
stale response rather than a blocked request. A caller that bypasses the cache fetches on its own
rather than joining or publishing a shared fetch.

The bypass context variable, managed through the controller's refresh context manager, forces
misses for the duration of a context. Whether a given read honours it defaults to the entry's
persistence: a persistent entry is not bypassed, an ordinary one is.

### Maintenance

A daily task removes expired entries and over-age stale rows. On setup the controller migrates the
schema in place, and falls back to dropping and recreating the table when the migration fails,
because the cache is disposable by definition. It then vacuums, but only when enough of the file is
reclaimable to be worth the startup cost. An oversized database is logged as a warning and kept.

## Related architecture docs

- [Overview](../../../docs/architecture/overview.md) for where the cache sits among the controllers.
- [Providers](../../../docs/architecture/providers.md) for the throttling and caching expectations
  on provider API calls.

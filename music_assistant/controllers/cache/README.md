# Cache Controller

This package provides a centralized caching layer backed by SQLite. All data stored in the cache goes through JSON serialization, ensuring consistent behavior regardless of when or how the data is retrieved.

## Responsibilities

- Store and retrieve JSON-serializable data with key/provider/category namespacing.
- Enforce data integrity: only `SerializableType` values (str, int, float, bool, None, list, dict) are accepted. Non-serializable objects raise `TypeError` immediately on write.
- Support expiration, checksums, and persistent entries that survive cache clears.
- Provide a `base_class` parameter on `get()` to automatically reconstruct model objects from cached dicts using `from_dict()`.
- Provide a `use_cache` decorator for transparently caching provider/controller method results with automatic serialization and deserialization based on type annotations.
- Provide `get_all()` for bulk reads: every non-expired entry for a provider/category as a `key -> data` mapping.
- Run scheduled cleanup of expired entries.
- Warn when the cache database exceeds the recommended maximum size on startup.

## Package Layout

- `controller.py`: main `CacheController` with get/set/delete/clear operations and database lifecycle.
- `constants.py`: shared constants (`DEFAULT_CACHE_EXPIRATION`, `MAX_CACHE_DB_SIZE_MB`, `DB_SCHEMA_VERSION`) and the `BYPASS_CACHE` context variable.
- `helpers.py`: the `use_cache` decorator for provider/controller methods.

## Design Notes

- There is no in-memory cache layer. SQLite with WAL mode, memory-mapped I/O, a sizeable page cache and `synchronous=normal` provides fast enough reads for all hot paths. This eliminates the inconsistency where an in-memory cache would return Python objects while the database returned deserialized dicts. The mmap ceiling and page cache are not fixed values: `get_sqlite_memory_settings()` in [helpers/database.py](../../helpers/database.py) scales both to the host's total RAM, so a memory-constrained device gets a small footprint while a large host keeps a big library hot.
- All data passes through `json_dumps` on write and `json_loads` on read. This means callers must use `.to_dict()` before storing model objects and `.from_dict()` (or the `base_class` parameter) after retrieval. Both `cache.get()` and the `use_cache` decorator accept a `base_class` parameter for automatic reconstruction.
- Cache entries are namespaced by `(category, provider, key)`. The `category` is an integer, `provider` and `key` are strings.
- Entries with `persistent=True` survive calls to `clear()` unless `include_persistent=True` is passed.
- Entries with `allow_expired_cache=True` survive the daily auto-cleanup task even after they have expired, so they remain available as fallback data for the stale-while-revalidate path of `@use_cache`. This is independent of `persistent`: `persistent` controls explicit `clear()` calls, `allow_expired_cache` controls auto-cleanup of expired rows.
- The `@use_cache` decorator accepts `allow_expired_cache=True` to enable stale-while-revalidate: an expired entry is returned immediately and a background refresh updates the cache for the next request. The `BYPASS_CACHE` context variable still forces a synchronous re-fetch.
- On a cache miss, `@use_cache` shares one execution of the wrapped method between concurrent callers on the same key, so a burst of identical requests costs a single provider call. Each caller gets its own copy of the result, because callers do adjust results in place (per-user podcast resume state, for one); the fetched objects themselves stay behind with the shared fetch, so the stored entry is written from data no caller has touched. A result that cannot be copied is shared instead, logged as a warning. A stale entry served under `allow_expired_cache` is likewise refreshed by a single background call, and a caller that bypasses the cache fetches on its own rather than joining or publishing a shared fetch.
- The `BYPASS_CACHE` context variable, managed through `handle_refresh()`, forces cache misses for the duration of a context — useful for refresh operations.
- `get_all(provider, category, base_class)` exists for callers that need to check a large number of keys at once (scanning a whole library, for instance). It issues one query and one deserialization batch instead of one of each per key, which is a different cost profile from a loop of `get()` calls rather than just a convenience wrapper.
- A daily cleanup task removes expired entries (unless `allow_expired_cache=True`). Databases that exceed the recommended max size (2GB) are logged with a warning at startup but kept in place.

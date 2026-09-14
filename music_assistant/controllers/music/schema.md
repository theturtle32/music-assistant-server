# Database schema and migrations

Part of the [music controller](README.md).

The schema version lives in `constants.py`. Tables, indexes and triggers are created in
`database.py`; the version-by-version upgrade steps live in `migrations.py`.

## Table groups

| Group | Holds |
|---|---|
| Media items | One table per media type, each with a companion full-text index over its normalized search column |
| Relationships | Album tracks, track artists, album artists, audiobook artists, genre mappings, genre exclusions |
| Provider linkage | Provider mappings, external id lookup |
| Analysis and history | Audio analysis, analysis failures, playlog |
| Bookkeeping | Settings, holding the stored schema version |

The full-text indexes are external-content tables, so they store no second copy of the data, and
triggers keep them in step. The migration tail rebuilds every index, which is what makes them
correct both on a first upgrade and after a step that rewrote rows while triggers were inactive.

Provider mappings are the central join between canonical library items and their sources. Each
entity query aggregates an item's mappings and external ids back into the JSON shapes the models
expect, so consumers see no difference from when those were columns.

A couple of table names survive only inside migrations, because the data they held was folded into
the analysis table and the originals dropped. You will meet them there and nowhere else.

## The playlog

The playlog is per user rather than global, and it has grown from a play history into the record
that recommendations, resume, scrobbling and recency all read. Alongside what was played and when,
it stores the artists as they were at play time, so recency can match the same song across releases
without a provider lookup, and it records whether the play was user-initiated and which queue it
came from.

Its uniqueness is per user, not global. A migration rebuilds the table where it still carries the
older global constraint, because SQLite cannot drop an inline unique constraint and the old shape
collides with the per-user upsert. Rows with no owning user cannot be kept under the newer schema
and are dropped in that rebuild. Nightly cleanup prunes old entries.

## Migrations

Anything older than schema 15 is refused outright. The database file is copied to a backup before
migrating.

If a migration raises, the file is deleted and recreated empty, the cache is cleared and a full
rescan is triggered. The user always ends up with a working library, and the backup is left in
place. A fresh install seeds the default genres instead. Startup finishes with a vacuum, skipped
unless enough of the file is reclaimable to be worth the time.

**A failed library migration costs the user a full rescan.** A step has to be idempotent, survive
missing and half-written values, and never raise.

## Schema versions on dev versus stable

The schema version is a single integer, so it can only describe one linear history. `stable`
normally inherits dev's numbering through releases, but a schema-changing bugfix backported to
`stable` is renumbered against stable's own lower counter, and from that point the same integer
means something different on each branch.

A database coming from `stable` then reports a version already higher than the gates of the dev
steps in the gap, so those steps never run and the schema objects they add stay missing. Table
creation cannot compensate, because it only creates tables that do not exist and never touches an
existing one. The user-visible result is a library that queries columns the database never got,
which has already happened once when a stable install was moved to the beta image.

Renumbering the stable backport to match dev does not fix it either: the database would then claim
to have run every dev step in between, which it genuinely never did. Encoding that correctly needs
a per-step applied-migrations ledger, which is out of proportion to how rarely this triggers.

So when backporting a schema change to `stable`:

1. Record in the backport PR that stable's schema version now diverges from dev's, and which value
   it took.
2. On `dev`, bump the schema version and add an idempotent guard step that re-adds every schema
   object introduced between the last shared version and stable's new one.
3. Gate that guard at dev's current version, never at stable's. Migration is skipped entirely when
   the stored version already equals the current one, so users who upgraded and broke are stamped
   at the current version and a lower gate would never fire for them.

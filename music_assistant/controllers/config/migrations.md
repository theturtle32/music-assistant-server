# Settings migrations

Part of the [config controller](README.md).

`migrations.py` transforms the raw settings dictionary before anything is parsed into config
objects.

**There is no schema version counter.** Each transform is independent and idempotent, gated on the
shape of the data it repairs, and carries a marker naming the release after which it can be
dropped. That keeps the accumulated set prunable without a version to reason about.

## Two phases

Most transforms run right after load, before config objects exist.

A second group runs later, from setup rather than load, because those transforms touch values that
have to be encrypted at rest and the encryption callbacks do not exist during load. Anything
moving a secret into place therefore has to wait for that phase.

## What a transform does

Three kinds, in practice:

- **Repairs**, such as an orphaned provider stub with no domain, or a self-referential protocol
  link. These fix data that no longer parses into anything sensible.
- **Renames**, where a key changed name but keeps its meaning.
- **Moves between scopes**, most notably the relocation of crossfade and volume normalization from
  the player to the queue, and the promotion of settings that became global.

A common pattern is repair-then-let-the-default-reassert: rather than computing a new value, the
transform clears a stored one so the current default applies. Clearing the stored name of players
the user never actually renamed is the clearest case, because it lets an improved default name
through instead of leaving it shadowed by the auto-generated name saved at creation time.

## Writing one

A migration runs once, against data written by a version you cannot inspect.

- Make it idempotent. It may run against data a previous version already fixed.
- Let it survive missing and half-written values. Do not assume a key exists or has the type you
  expect.
- Never let it raise.
- Tag it with the release after which it can be removed.

Config entries and database rows are live user data. A renamed key, a changed type, a value that
moves scope or a dropped column breaks only the installs that already hold data, and no test
catches it. When a change touches stored data, agree the migration with the developer before
treating the work as done.

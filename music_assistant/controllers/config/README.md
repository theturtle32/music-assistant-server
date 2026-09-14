# Config controller

This package owns every persistent setting in Music Assistant: server options, provider
credentials, per-player tuning and per-queue playback preferences. It is the first thing the
server initializes, because every other component reads its settings from here.

It is deliberately not a `CoreController`. Core controllers are handed a `CoreConfig` when they
start, and only the config controller can produce one, so it needs a simpler lifecycle that runs
before the core controller infrastructure exists.

## Deep dives

- [setup-flows.md](setup-flows.md): the interactive setup and reconfigure engine.
- [migrations.md](migrations.md): the settings transforms and how to write one.
- [scopes.md](scopes.md): setup data versus values, injected entries, global fallbacks.

## Package layout

`controller.py` holds the base class and composes the rest as mixins. Each mixin owns one config
scope and declares `TYPE_CHECKING` stubs for the base attributes it uses, so the split stays
type-checkable without a shared abstract base.

| Module | Role |
|---|---|
| `controller.py` | `settings.json` load and save, the hierarchical get/set interface, encryption, onboarding |
| `constants.py` | Save debounce, base keys, the queue config owner |
| `helpers.py` | Translation-owner stamping and derived provider status |
| `core.py` | Core module config and its action dispatch |
| `providers.py` | Provider config, setup data reads, derived status, load-time seeding and rehydration |
| `players.py` | Player config plus the injected protocol-output entries |
| `queues.py` | Per-queue config and global-value resolution |
| `dsp.py` | Per-player DSP config and the shared DSP presets |
| `flows.py` | The interactive setup and reconfigure flow engine |
| `migrations.py` | One-off `settings.json` transforms applied on load |

## Storage and durability

Settings live in `settings.json` under the storage path. Values are addressed by `/`-separated
key paths that traverse nested dictionaries.

Writes are debounced by a few seconds and collapse repeated changes into one write. Callers that
must not proceed until the change is on disk use the awaitable form, which cancels any pending
debounce and skips the write when a concurrent save already persisted that generation. Shutdown
compares the requested and written generations and only writes when the latest change never
reached disk.

Every write is atomic and backed up. The controller serializes to a temporary file and fsyncs it,
rotates the current file to a backup but only when that file still parses as JSON, renames the
temporary file into place, and then fsyncs the directory where the platform supports it. A crash
can therefore never leave a truncated primary file, and a corrupt leftover can never overwrite a
good backup. Loading tries the primary file and then the backup, and starts with empty storage
when neither is readable.

Structured data lives in three SQLite databases rather than in `settings.json`: the media library,
the cache, and the users and tokens store owned by the webserver. They share the connection
wrapper in [helpers/database.py](../../helpers/database.py),
which tunes SQLite for throughput over durability and scales its page cache and mmap ceiling to
the host's total RAM.

## Settings migrations

`migrations.py` transforms the raw settings dictionary right after load, before anything is parsed
into config objects, with a second group running later for values that must be encrypted at rest.
There is no schema version counter; each transform is independent and idempotent. See
[migrations.md](migrations.md).

## The four config scopes

All four inherit from `Config` in the shared models package, which holds the entry values and the
parse, update and validate behaviour.

| Scope | Stored under | Notable fields |
|---|---|---|
| `CoreConfig` | One per configurable core controller | Domain, last error |
| `ProviderConfig` | One per provider instance | Type, domain, instance id, enabled, name, last error, derived status, setup data |
| `PlayerConfig` | One per player | Owning provider, player id, enabled, name, player type, setup data |
| `PlayerQueueConfig` | One per queue, matching the player id | Nothing beyond the values themselves |

Parsing stamps every entry with a translation owner derived from the scope, and that namespace is
what resolves the entry's localized label and description when it is serialized.

Provider status is computed on the API read path rather than stored, derived from whether the
instance is disabled, loaded, or carries a persisted error.

[scopes.md](scopes.md) covers the split between setup data and config values, the entries one
scope injects into another, and how a per-queue setting falls back to its global default.

## Config entries

Every setting is described by a `ConfigEntry` from the shared models package, carrying its type,
default, options, range, UI category, visibility flags, dependencies and whether a change requires
a reload. Labels are never authored in code; they resolve from the translation catalog, and a
pre-commit hook fails the build when an entry hardcodes one. See [scopes.md](scopes.md).

## DSP configuration

Per-player DSP is stored separately from the player config, as a serialized `DSPConfig` rather than
as entry values, because a filter chain is a list of heterogeneous typed objects that the flat entry
model cannot express. Presets are a shallow link: a player stores a copy of the preset plus the id
it came from, so editing a preset clears that id on every player that used it without changing
their audio. Impulse response files for the convolution filter are managed here too.

How the chain is compiled into FFmpeg parameters belongs to the streaming pipeline. See
[controllers/streams](../streams/README.md).

## Setup flows

Anything interactive, meaning credentials, OAuth logins and pairing, runs through the setup flow
engine in `flows.py`. A flow is one plain coroutine in the provider's `setup_flow.py` that
publishes a step and suspends until the user responds. See [setup-flows.md](setup-flows.md).

## Encryption

Secure string entries are encrypted at rest with Fernet, under a dedicated key generated on first
run and stored in the settings file. An unreadable key is replaced and the legacy migration flag is
reset, so anything still decryptable is re-encrypted on the next pass. Encryption and decryption
happen through callbacks the controller installs on the models, which hold no key material
themselves. Setup data is encrypted independently of any entry metadata, because setup data has no
entry to key off.

Clients never receive a secure value in either form. Serialization substitutes a placeholder and
drops setup data entirely, so a client can only set a new value.

## Change propagation

Saving a config compares the new values against the current ones and returns the set of changed
keys. When something changed, the config is persisted first and the owner is notified second.
Persisting first matters because a reload can cancel the calling task, and the core and provider
paths restore the previous raw config when the update raises.

The owner then decides whether to reload. A core controller reloads when a changed entry declares
that it requires one. A provider reloads on any non-log-level value change without consulting that
flag, because provider reloads are cheap and most providers read their config once at setup. For a
queue there is no owner to reload, so the flag means "restart playback on this queue" instead. Both
reload paths run after a one-second delay under a shared task id, which collapses rapid-fire changes
into a single reload. A log level change applies immediately without a reload.

Raw writes bypass all of this. Providers use them to persist runtime state such as a rotated auth
token, without validation and without triggering a reload.

## Related architecture docs

- [Providers](../../../docs/architecture/providers.md) for the provider error model and the load lifecycle.
- [Events and commands](../../../docs/architecture/events-and-commands.md) for how config commands are dispatched.
- [Overview](../../../docs/architecture/overview.md) for where the config controller sits in startup.

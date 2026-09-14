# Config controller

This package owns every persistent setting in Music Assistant: server options, provider
credentials, per-player tuning and per-queue playback preferences. It is the first thing the
server initializes, because every other component reads its settings from here.

It is deliberately not a `CoreController`. Core controllers are handed a `CoreConfig` when they
start, and only the config controller can produce one, so it needs a simpler lifecycle that runs
before the core controller infrastructure exists.

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
into config objects. There is no schema version counter. Each transform is independent and
idempotent, gated on the shape of the data it repairs, and carries a marker naming the release
after which it can be dropped. Transforms cover repairs such as an orphaned provider stub, renames,
and moves between scopes such as the relocation of crossfade and volume normalization from the
player to the queue.

A second group runs later, from setup rather than load, because those transforms touch values that
have to be encrypted at rest and the encryption callbacks do not exist yet during load.

Migrations run once against data written by a version you cannot inspect. Keep them idempotent,
let them survive missing and half-written values, and never let them raise.

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

### Setup data is not config values

Values hold ongoing options: the settings a user revisits in a provider's settings form, each one
described by a `ConfigEntry`. Setup data holds one-time setup input such as credentials, OAuth
tokens and pairing state. Only the setup flow engine writes it, its string values are encrypted at
rest, and it is stripped from every API payload.

Because a provider declares its entries from an instance method, the real entries only exist once
the instance does. Two helpers bridge that gap during load: stored raw values are seeded as
passthrough entries so early reads see them, and the config is re-parsed against the full entry set
once the instance is constructed.

### Injected entries

A player's config surface is not only its own. Entries belonging to a linked protocol player are
injected into the parent with a prefix so a client can configure a whole device from one endpoint,
and they are never persisted on the parent. Plugins that bind their audio sources to individual
players contribute a toggle to each eligible player, so "is this enabled on this speaker" is
answered from the speaker's settings page.

### Global values with per-queue overrides

Queue settings are a tri-state select rather than a boolean. The `player_queues` core module holds
the global value, and each queue's matching entry additionally offers `global`, which is also its
default. Resolution falls through to the core value when the queue stores `global` or stores
nothing. Numeric settings such as crossfade duration cannot carry the extra option, so they stay
global only. The schemas for both sides are built in
[controllers/player_queues](../player_queues).

## Config entries

Every setting is described by a `ConfigEntry` from the shared models package. The entry carries its
type, default, options, range, UI category, visibility flags, dependencies on other entries, and
whether changing it requires a reload.

Labels and descriptions are never authored in code. They resolve from the translation catalog under
the entry's translation owner, and a pre-commit hook fails the build when an entry hardcodes label
or description text instead of using `strings.json`. See
[controllers/translations](../translations/README.md).

`music_assistant/constants.py` holds a library of pre-built entries that providers and players
compose their config from, along with pre-derived variants for players that must pin or hide a
setting. A provider's full entry list is the server defaults plus whatever the provider returns,
and for music providers the library-sync toggles derived from its features.

Action entries are one-shot buttons rather than stored values. Invoking one routes to the owner,
which can report an outcome, report nothing, or return re-rendered entries.

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
engine in `flows.py`. A flow is authored as one plain coroutine in the provider's `setup_flow.py`,
and the session handle it receives publishes a step and suspends until the user responds. Steps
render a form, send the user to an external URL and wait for the callback, show progress, or
finish by persisting the collected values and creating or reloading the target. Authors signal
outcomes with exceptions rather than return codes.

The engine keeps one flow per target, so starting a new one aborts any lingering flow for the same
provider or player. Aborting cancels the flow task first, so an author's cleanup runs before the
terminal step is published. Idle flows are swept after fifteen minutes unless the current step
advertises a longer countdown. A provider that ships no `setup_flow.py` needs no input, so creating
it returns a synthesized finish step and clients keep one code path for every provider. A player
whose own setup is a no-op but which wraps protocol children that need pairing delegates to the
child's flow. Every finish handler snapshots the existing setup data and restores it when creating
or reloading the target fails.

Flow steps reach clients as events. Because a step can carry prefilled values and OAuth URLs, the
WebSocket layer filters those events by scope instead of broadcasting them.

The authoring guide for provider setup flows lives at
[developers.music-assistant.io](https://developers.music-assistant.io/setup-flows/).

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

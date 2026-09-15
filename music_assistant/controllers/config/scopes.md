# Config scopes and entries

Part of the [config controller](README.md).

## Setup data is not config values

Values hold ongoing options: the settings a user revisits in a provider's settings form, each one
described by a `ConfigEntry`. Setup data holds one-time setup input such as credentials, OAuth
tokens and pairing state. Only the setup flow engine writes it, its string values are encrypted at
rest, and it is stripped from every API payload.

Because a provider declares its entries from an instance method, the real entries only exist once
the instance does. Two helpers bridge that gap during load: stored raw values are seeded as
passthrough entries so early reads see them, and the config is re-parsed against the full entry set
once the instance is constructed.

## Injected entries

A player's config surface is not only its own. Entries belonging to a linked protocol player are
injected into the parent with a prefix so a client can configure a whole device from one endpoint,
and they are never persisted on the parent. Plugins that bind their audio sources to individual
players contribute a toggle to each eligible player, so "is this enabled on this speaker" is
answered from the speaker's settings page.

## Global values with per-queue overrides

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

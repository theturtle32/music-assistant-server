# Translations controller

Resolves translatable strings at runtime. Authoring and building happen in the repository; this
controller is the runtime half.

## Deep dives

- [authoring.md](authoring.md): where to add a string, the build step, and the reference mechanism.

## Loading

Setup discovers the available locale files by name without parsing them, computes the available
locale list, and eagerly loads the English source as the final fallback. Translated locales load
lazily on first use, each behind a per-locale lock so concurrent cold loads of the same locale do
not both read the file. After that, every lookup is an in-memory dictionary read.

A locale can be warmed up front, and the WebSocket and HTTP layers do exactly that when a
connection declares its locale, so no lookup during serialization ever touches disk.

**This controller is set up first, on its own, before the other core controllers start
concurrently.** Every other controller can be serialized, and serialization resolves translations,
so none of them may start before the catalogue exists.

## The candidate chain

Keys are fully qualified with an owner root: shared, core plus domain, or provider plus domain.
Callers usually pass a relative key plus an owner hint, which expands into an ordered candidate
list, most specific first:

1. The owner's own string.
2. The domain-only form, for a multi-instance owner whose id carries an instance suffix.
3. The shared string.
4. The bare key.

Any candidate ending in a name segment also gets a fallback with that segment stripped, which is
what lets an authoring file write either form.

Each candidate is probed across locales in turn: the requested locale, then its base language, then
the English source. Resolution returns nothing when there is no match and **never raises**, so a
caller keeps whatever English value it already had rather than displaying a raw key.

That fallback ladder is what makes the build-time reference mechanism work. An owner that declares
its string is a reference has its key omitted from the catalogue entirely, and the runtime finds
the shared string further down the chain.

## Translation owners

Both base classes expose the namespace their strings resolve under, derived from the domain. Core
controllers resolve under a core namespace and providers under a provider namespace.

Anything carrying a relative key passes its owner alongside it. Provider errors carry the key, its
arguments and the owner together, which is how a provider-raised error arrives at a client already
localized. A background task's owner is stamped by the tasks controller and omitted from
serialization, because it is resolution machinery rather than data a client needs.

## Resolution happens during serialization

A context variable holds the resolver, and models call a helper from their post-serialize hook. The
server binds the resolver for the duration of each outbound serialization: the WebSocket binds the
connection's locale, and HTTP binds the locale derived from the request's language header.

Three properties fall out of doing it that way.

**Models localize themselves.** An entry, a task or a media item swaps its own label, name or
description for the localized string as it serializes. No controller passes a locale anywhere.

**Internal serialization is untouched.** A plain serialization with no resolver bound, which is
what caching, item mappings and config storage use, keeps the English source *and* keeps the
translation machinery in the output. That is essential: a cached object has to still be localizable
when it is later served to a different connection with a different locale. Localized API output
strips the machinery instead.

**Failures are invisible.** Resolution catches everything and returns nothing, because it must
never break serialization. A broken catalogue degrades to English rather than to an error.

## Choosing a locale per connection

A WebSocket client can pass a locale when it authenticates, or set it at any time afterwards. That
setter is one of only two commands handled before the command registry is consulted, precisely
because it mutates connection state rather than invoking a controller.

HTTP derives the locale per request from the language header, taking the highest-priority tag.

## Two locale lists, easily conflated

| List | Means |
|---|---|
| UI locales, discovered from the translation files | Which languages the server can localize its own output into |
| Metadata language, in the metadata controller's constants | Which language to request from metadata providers, and the locale used for reverse lookup |

The metadata list is larger, because asking a streaming provider for German metadata does not
require anyone to have translated this project's UI into German. Neither list should be hardcoded
into documentation; read the translations directory and the metadata constants.

## Reverse lookup

One place where translation runs backwards. Genre and playlist names for built-in content are
themselves translatable, so a user searching for a genre by the name on screen would find nothing,
because the library stores the canonical English name.

Reverse lookup scans the configured metadata language's bundle for genre and playlist name keys
whose localized value contains the query, and returns the English source strings for the matches. A
text search that comes back empty retries against those.

Three deliberate limits. Only genres and playlists are considered, because they are the searchable
library media types, while browse and recommendation folder titles are display-only and never
library items. The locale is the metadata language rather than the connection locale, since it
doubles as the fallback search locale. And an English or untranslatable language returns nothing,
because a literal search already covers English.

## Related architecture docs

- [Localization](../../../docs/architecture/localization.md) for the end-to-end pipeline.
- [Configuration](../../../docs/architecture/configuration.md) for how config entry labels resolve.

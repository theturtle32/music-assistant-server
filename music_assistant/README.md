# The server package

Everything that runs inside the Music Assistant server process. This file covers the package root
itself: the hub object, the event bus and command registry it owns, and where the rest of the code
lives.

## Deep dives

- [The event bus and the command registry](events.md): the event bus, the command registry, and the
  enum members that look live but are not.

## Layout

| Path | Holds |
|---|---|
| `mass.py` | The `MusicAssistant` hub: the controllers, the event bus, the command registry, the provider registry, task tracking, the shared HTTP sessions |
| `__main__.py` | The command line entry point: argument parsing, logging setup, storage paths, the run loop |
| `constants.py` | Cross-cutting constants and config keys shared by more than one package |
| `controllers/` | The core controllers, one directory each, every one with its own README |
| `providers/` | Every provider, one directory each, with a manifest and often a README |
| `models/` | The base classes providers subclass, and the runtime player model |
| `helpers/` | Utilities shared across packages. Check here before writing a new one |
| `translations/` | The built translation catalogue, one file per locale |
| `strings.json` | The source strings this package owns |

## The hub

One object is the nucleus of the server, and every controller and provider holds a reference to it.
Anything reachable from anywhere is reachable through it, which is what lets a provider be
constructed with a single argument instead of a dependency graph.

It is created once by the entry point, or directly by an embedding host, and it owns the
lifecycle: the controllers are constructed on it in dependency order, and shutdown reverses that.
See [the architecture overview](../docs/architecture/overview.md) for the ordering and why each
step sits where it does.

Three things on it are worth knowing before reading any other package.

**The command registry.** Every API command anywhere in the codebase registers into one dictionary
on the hub, scanned for at startup. Both API transports dispatch through it.

**The event bus.** A set of subscribers with optional filters, signalled synchronously. See
[The event bus and the command registry](events.md).

**Task tracking.** Two primitives, one for a tracked task and one for a delayed call, both keyed by
an optional id so a repeat call replaces the pending one. Everything they create is cancelled at
shutdown. Both refuse to run off the event loop thread, because neither the subscriber set nor the
task dictionaries are thread-safe and failing loudly beats corrupting them.

## Models and helpers

`models/` holds the contracts rather than the implementations: the provider base classes a provider
author subclasses, and the runtime `Player` model a player provider reports state onto. The
client-facing dataclasses live in the separate `music-assistant-models` package, which the frontend
and the Python client share, so a change there is a wire-format change across three repositories.

`helpers/` is shared utility code with no single owner. A few helpers are substantial enough to be
subsystems in their own right and carry their own documentation:
[Shared playback sessions](helpers/shared-playback.md) for group listening sessions. Others are
documented where they are used: the scrobbler base in
[plugins](../docs/architecture/plugins.md), the audio and ffmpeg helpers in
[controllers/streams](controllers/streams/README.md), and the comparison and external-id helpers in
[Matching and merging](controllers/music/media/matching.md).

## Related architecture docs

- [Overview](../docs/architecture/overview.md) for the hub, the controller map and startup.
- [Events and commands](../docs/architecture/events-and-commands.md) for the big picture.
- [Providers](../docs/architecture/providers.md) for what lives under `providers/`.
- [Architecture index](../docs/architecture/README.md) for every page and package doc.

# The event bus and the command registry

Part of [the server package](README.md). The rationale and the big picture are in
[events and commands](../docs/architecture/events-and-commands.md); this covers the mechanics and
the things that will mislead you if you read only the enum.

## Signalling

An event carries a type, an optional object id and an optional payload, and is signalled through
the hub. Signalling is synchronous: subscribers matching the filters are walked in one pass.

A **synchronous** callback is invoked inline, so it holds up the walk and everything after it. An
**async** callback is wrapped in a tracked task instead, which the bus does by recording whether
each callback is a coroutine function at subscribe time rather than re-deriving it on every event.
That matters because the chatty event types fire often enough for reflection per subscriber per
event to show up.

Two guards sit at the top. Signalling verifies it is on the event loop thread, because the
subscriber set is not thread-safe. And events are dropped once the server is closing, so shutdown
does not generate traffic nobody will consume.

## Subscribing

Subscribing takes a callback plus optional filters on event type and object id, and returns a
callable that removes the listener. Filtering at subscription time rather than inside the callback
is what keeps a high-frequency event type cheap for the subscribers that do not care about it.

The object id is whatever identifies the subject: a player id, a queue id or a URI.

## Provider events

A provider that needs to push its own state to clients signals a generic provider event under its
own identity rather than having a member added to the shared enum. The object id is the provider's
instance id, optionally suffixed with a sub-scope so one provider can run more than one event
stream. The payload is provider-defined.

That keeps the shared vocabulary about things the core system does, while still letting a plugin
talk to its own frontend. The quiz plugin is the fullest example, broadcasting whole game state
this way; see [providers/music_quiz](providers/music_quiz/README.md).

## Members that look live but are not

Reading the enum in the models package suggests these are in use. They are not, and each is a
different kind of leftover.

| Member | Reality |
|---|---|
| `AUTH_SESSION` | Retired with the auth-popup mechanism it belonged to. The member survives for wire compatibility; nothing emits or subscribes to it |
| `SYNC_TASKS_UPDATED` | Reserved. Defined in the models package, referenced nowhere in server code. Sync progress reaches clients as a task update instead |
| `SHUTDOWN` | Deprecated in favour of the core state event. Nothing signals it any more, but `helpers/aiohttp_client.py` still *subscribes* to it to close its shared DNS resolver |

The last one is worth a second look before anyone tidies it away. That subscription is the only
call site of the resolver's real close, so the cleanup no longer runs at all. It is harmless in
practice, since the process is exiting anyway, but it is a dangling subscription rather than a
cosmetic enum remnant: removing the member without removing the subscriber would break the import,
and removing the subscriber is the actual fix.

## There is no position-jump event

A player position moving outside normal playback progression, from a seek or a buffer correction,
does **not** get its own event type.

The player controller is notified so it can re-base the active queue's timing on the fresh position
and nudge related players, but that notification is internal. The state update that follows is what
emits the ordinary player update, and clients detect the discontinuity from the position anchors
carried in the state snapshot. See [controllers/players](controllers/players/README.md).

## A name that means two different things

Several provider libraries define their own event type enums, and `aiosonos` and `aioslimproto`
both do, with members like player-connected and group-updated that have nothing to do with this bus.
The in-tree providers alias them on import to keep the two apart, but a grep for the bare name
across the tree still surfaces both, and a provider added later may not alias.

## Commands

The command registry is the imperative counterpart, and it is one dictionary on the hub keyed by a
dotted name. A method anywhere in the codebase is registered by decorating it, declaring whether it
requires authentication and which scope it needs.

Registration happens by scanning the constructed controllers and loaded providers at startup, after
the controllers exist and before the webserver starts, which is why a handler always exists by the
time a request can arrive. Arguments are coerced from the command's own type hints, and the
generated API documentation is built from the same registry, so a command's docstring is public API
documentation written for its caller.

Two commands are handled before the registry is consulted, because they mutate connection state
rather than invoking anything: setting the connection's locale is one. See
[controllers/webserver](controllers/webserver/README.md) for dispatch and connection handling.

## Related architecture docs

- [Events and commands](../docs/architecture/events-and-commands.md) for the big picture.
- [API and auth](../docs/architecture/api-and-auth.md) for the transports and the scope model.
- [Operations](../docs/architecture/operations.md) for the tasks controller, which is a different
  thing from the hub's task helper.

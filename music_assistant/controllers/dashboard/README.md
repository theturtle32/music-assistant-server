# Dashboard controller

Casts a Music Assistant dashboard, the party screen being the one that exists today, onto a display
device: a TV running a cast receiver, a tablet, a kiosk browser.

It is a small controller with an unusually careful lifecycle, because a display is a thing that
walks out of the room.

## Two ways to register

A display makes itself available by registering, and there are two shapes.

| Registration | Made by | Shown by |
|---|---|---|
| In-server | Another provider, handing over callbacks | Calling the callback directly |
| Over the API | A client, over its WebSocket | Emitting an event the client reacts to |

The first covers a cast device the server can drive itself. The second covers a client that can
display a dashboard but has to be told to, and which resolves its own URL rather than being handed
one.

**An API registration is deliberately WebSocket-only.** The registration belongs to the connection
that made it, so a display dropping off the network takes its registration and any session with it.
Allowing it over the plain request endpoint would leave phantom endpoints the server believes it can
still cast to, with nothing to notice they are gone.

## Sessions

Showing a dashboard opens a session against the device, and hiding it closes one. Sessions are held
in memory only, since they describe what is on a screen right now and mean nothing after a restart.

Showing and hiding require the scope for inviting people, not a display or configuration scope. That
matches what the feature is: putting a dashboard on a screen is how guests are brought into a party
session, so it is the same capability as inviting them.

Reading the available dashboards and the current sessions needs no such scope, so a client can show
what is running without being able to change it.

The intent is validated before either branch runs, so an in-server and an API registration reject
the same bad request identically rather than failing in different places. A consumer that cannot
resolve its own URL raises before anything is shown, rather than putting a broken screen up.

## Related architecture docs

- [The API and authentication](../../../docs/architecture/api-and-auth.md) for the scope model and
  why registration is bound to a connection.
- [Events and commands](../../../docs/architecture/events-and-commands.md) for the event an API
  registration is driven by.
- [Plugins](../../../docs/architecture/plugins.md) for the party plugin that puts a dashboard up.

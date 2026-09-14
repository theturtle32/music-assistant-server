# Connecting a client

Part of the [Sendspin provider](README.md). Three paths reach the same protocol server, and only one
of them is this provider's concern.

| Client | Path | Implemented in |
|---|---|---|
| Hardware or a native app on the LAN | Straight to the protocol server's own port | Here |
| A browser on the LAN | An authenticated WebSocket proxy on the main webserver, forwarding frames both ways | [controllers/webserver](../../controllers/webserver/README.md) |
| Anything outside the LAN | A labelled WebRTC data channel, bridged by the remote access gateway to the same internal server | [controllers/webserver/remote-access.md](../../controllers/webserver/remote-access.md) |

## Why two of them live elsewhere

A browser cannot open a raw socket to an arbitrary port, and a client outside the network cannot
reach one at all. Both therefore need a carrier.

Putting those carriers in the webserver rather than here means they **reuse the authentication that
already exists**, and the remote path reuses the existing connection-brokering stack. This provider
consequently registers no signalling commands and adds no dependency for it, which is the whole
reason the split is worth the indirection.

## Authenticating on the proxied path

The proxy authenticates the same way the main API does. An ingress request is trusted from its
headers; any other client must send an authentication message as its **first** frame or the socket
is closed.

That first message also carries the client identifier that binds the socket to a specific player,
so authentication and player binding happen in one step rather than leaving a window where an
authenticated socket belongs to nobody.

After that frame the socket is a plain protocol channel with nothing proxy-specific about it, which
is what lets a client library be written against the protocol alone.

## Writing a client

A browser connects to the proxy endpoint on the main webserver rather than to the protocol port, and
sends its authentication message first. Everything after that is ordinary protocol traffic, which a
client library can handle without knowing a proxy is involved.

A native app on the local network connects directly to the protocol port. An app that also has to
work away from home reaches the server through remote access, where the data channel carries the
same protocol transparently, with no app-side signalling against this provider.

Hardware devices connect directly, the same way a native app does.

The [_demo_sendspin_clients](../_demo_sendspin_clients/README.md) directory holds worked examples.

## Related

- [API and auth](../../../docs/architecture/api-and-auth.md) for the scope and token model the proxy
  reuses.
- [controllers/webserver/remote-access.md](../../controllers/webserver/remote-access.md) for channel
  labels, which are a compatibility surface.

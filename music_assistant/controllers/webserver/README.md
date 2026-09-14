# Webserver controller

Hosts the API, the frontend, and the authentication system, and owns remote access. It runs on
port 8095 by default. Audio is deliberately not served from here; see
[controllers/streams](../streams/README.md) for why that is a separate server.

## Module layout

| Module | Role |
|---|---|
| `controller.py` | The `WebserverController`: HTTP server lifecycle, route registration, WebSocket client management |
| `auth.py` | `AuthenticationManager`: users, roles, tokens, join codes, and the auth database |
| `websocket_client.py` | One connection's lifecycle: authentication, command routing, event subscription |
| `sendspin_proxy.py` | Authenticated WebSocket proxy to the internal Sendspin server |
| `api_docs.py` | Generates the API documentation from command docstrings and type hints |
| `helpers/auth_middleware.py` | Per-handler request authentication, user context, ingress detection, role to scope mapping |
| `helpers/auth_providers.py` | Login provider base classes, the builtin provider, the Home Assistant OAuth provider, rate limiting |
| `helpers/ssl.py` | SSL context creation and certificate verification |
| `remote_access/` | The WebRTC gateway and its signaling client |

What it serves: the frontend app, the WebSocket API, the HTTP JSON-RPC API, the login and OAuth
routes, the setup route, the generated API documentation, the image proxy and audio preview
endpoints, and the Sendspin proxy. Plugins can add their own paths as dynamic routes, which is how
the MCP server mounts without standing up a second server.

## The command model

Every API command is a method decorated as such anywhere in the codebase, which registers it in one
registry under a dotted name. Both transports dispatch through that same registry, so a command
behaves identically over the WebSocket and over HTTP, including its authentication and scope
requirements. The generated API documentation is built from the same registry, which is why a new
command documents itself from its docstring and type hints.

The WebSocket carries events as well as commands, so a client that needs to react to state changes
uses it; the HTTP endpoint exists for simple request and response callers. See
[events and commands](../../../docs/architecture/events-and-commands.md).

Some subsystems expose commands but no routes of their own. The dashboard controller is one, and
its registration is deliberately WebSocket-only: a registration is owned by a connection, so a
display that drops off the network takes its registration and session with it instead of lingering
as a phantom endpoint.

## Authentication

### Users, roles and scopes

The API gates on scopes, never on roles. A role grants a set of scopes, and each command declares
the scope it requires. Four roles exist: an administrator with everything, a standard user whose
reach can be narrowed further by player and provider filters, a guest limited to reading the
library and controlling playback, and a service account used by the Home Assistant integration,
which adds player configuration, reading user accounts and impersonation.

A command may allow impersonation, which lets a sufficiently privileged caller execute it on behalf
of another user.

### Tokens

Tokens are signed JWTs. The database stores only a hash of each issued token, so a token can be
revoked without ever being stored. Revocation disconnects the holder's WebSocket immediately, as
does disabling a user.

Short-lived tokens renew on use against a sliding window, capped by an absolute lifetime after
which the user must authenticate again. Long-lived tokens do not renew and exist for integrations.
Guest tokens are short and never renew.

### Ways in

First run with no users redirects to the setup route, where the first administrator is created.
Under Home Assistant ingress there is no setup step at all: the request carries HA user headers, the
user is created on first access, and no password is involved. Ingress is served by a dedicated site
bound to the internal Docker network.

Standard login posts credentials and receives a token. The Home Assistant OAuth flow redirects to
HA for consent and returns through the callback route, where the code is exchanged, the user is
found or created, and a token comes back on the redirect. Remote clients use that same flow rather
than a separate path; the return URL a client supplies is classified as trusted, external or
blocked before a token is appended to it, which is what makes the redirect safe across origins.

On the WebSocket, the first command must authenticate. Everything after that runs in the
authenticated user's context.

Passwords are hashed with a salt combining the random user id and the server id. Failed logins back
off progressively.

## Remote access

Remote access reaches an instance from anywhere without port forwarding or a VPN. A cloud signaling
server exchanges the WebRTC handshake, and a local gateway bridges data channel messages to the
local WebSocket API, so authentication and authorization work exactly as they do locally. Traffic
is encrypted end to end and the signaling server only routes handshake messages.

The remote id identifies an instance. It is derived from the fingerprint of the instance's
persisted WebRTC certificate rather than stored separately, so it is stable for as long as the
certificate is, and it can be derived without loading the native WebRTC library, which is what lets
it be reported while remote access is off.

Two modes. The basic mode uses public STUN servers, needs no subscription, and works in most
networks, though it can fail behind symmetric NAT or a firewall that blocks UDP. The optimized mode
uses Home Assistant Cloud STUN and TURN servers, which relay when a direct connection is impossible.
The mode switches automatically when the cloud subscription status changes.

### Data channels

One remote session multiplexes several data channels over one peer connection, routed by label. A
bridged channel is pumped both ways to a local WebSocket, which is how the Sendspin player and live
announcements work. A channel served in the gateway itself handles proxied HTTP requests for album
art and other assets. Closing one of those tears down only that channel.

The client's API channel has no fixed label. The first channel with an unrecognised label becomes
the API channel and is bridged to the WebSocket API; any later unrecognised label is refused,
because taking it for a second API channel would replace the live bridge and break the session. The
API channel shares the session's lifetime.

Proxied HTTP replies go back on the channel they arrived on, which is what keeps older clients
working without version negotiation. The framing differs by channel: on the API channel the body is
hex-encoded into one JSON message, which costs several times the image's size once chunking is
applied, while the dedicated proxy channel sends a JSON header followed by the body as raw binary
messages, costing the image's own size and no more. Those binary messages carry no request id, so
the gateway holds the channel for a whole reply rather than interleaving. A client that stops
draining gets a bounded time per frame, after which the reply is abandoned where it stands, so a
reply can end short of its announced size and the next header is what follows.

Bulk frames are sized to the channel's maximum message size, which is the lower of our own ceiling
and what the peer advertises, and one library assumes a small default when nothing is advertised. A
client therefore has to expect chunking well below the ceiling.

**Adding a new channel label is not backwards compatible on its own.** A server from before the
routing table existed mistakes an unknown label for the API channel, which breaks the whole remote
session rather than just the new feature. A client must feature-detect on the schema version from
the server info before opening one, and adding a label means bumping that version and gating the
client on the new value.

## Security posture

All API access requires authentication except under ingress, where Home Assistant has already done
it. Enforcement is identical on both transports because both dispatch through the same registry.
Users can be restricted to specific players and providers on top of their scopes.

The server speaks plain HTTP by default because it runs on the local network; TLS can be enabled by
supplying a certificate and key. It should not be exposed directly to the internet. Use remote
access, a reverse proxy, or a VPN.

## Adding to the API

A new command is a decorated method on the owning controller or provider, declaring whether it
requires authentication and which scope it needs. It appears in the generated documentation
automatically. A new HTTP route is registered on the controller, or as a dynamic route by a
provider.

A new login provider subclasses the base in `helpers/auth_providers.py`, implements authentication
and, if it is an OAuth provider, the authorization URL and callback, and is registered with the
authentication manager.

Changing the auth database schema means bumping its version and adding a migration step. A
migration runs once against data written by a version you cannot inspect, so keep it idempotent and
never let it raise.

The running server publishes its own docs at `/api-docs`, including a command reference, the
schemas and an interactive explorer.

## Related architecture docs

- [API and auth](../../../docs/architecture/api-and-auth.md) for the big picture of the API surface, scopes and users.
- [Events and commands](../../../docs/architecture/events-and-commands.md) for the event bus and the command registry.
- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for the MCP server that mounts here.
- [Overview](../../../docs/architecture/overview.md) for where the webserver sits in startup.

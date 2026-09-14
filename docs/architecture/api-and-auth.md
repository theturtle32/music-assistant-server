# The API and authentication

One command registry, two transports, and an authorization model built on scopes rather than roles.

## Two transports, one registry

Both the WebSocket and the HTTP endpoint dispatch through the same command registry, so a command
behaves identically on either, including its authentication and its required scope. The generated
API documentation comes from that registry too.

Use the WebSocket when you need events as well as commands; use HTTP for simple request and
response. See [events-and-commands.md](events-and-commands.md).

Audio is deliberately served from a separate HTTP-only server with no TLS and no authentication,
because embedded players struggle with handshakes and cannot hold credentials. Stream URLs carry a
session id instead, which is what rejects a stale request. See [playback.md](playback.md).

## Authorization is by scope

A scope is a named capability. Each command declares the one it requires, and a role grants a set
of them.

**The check has no hierarchy.** There is no prefix matching, no per-user override and no
inheritance: a user either holds the exact scope their role grants, or they do not. One
everything-scope is the single special case.

Two defaults make that fail closed. An unrecognized scope string, which is what a value from a
newer server or a typo in stored config produces, deserializes to a member that can never satisfy
a check rather than raising or matching by accident. And a role id that is not in the mapping
resolves to an empty set, which is what leaves room for custom roles without them accidentally
granting anything.

Roles are typed as plain strings for that reason rather than as a closed enum.

## The four roles

| Role | Is |
|---|---|
| Admin | Everything |
| User | A normal account: library writes, read-only config, inviting guests |
| Guest | Read the library, and **control playback** |
| Service | A user plus player-config write, reading users, and impersonation |

Two of those deserve explanation.

**A guest can control playback**, and that is deliberate. The guest-facing features, meaning party
mode, the quiz and the dashboard viewer, all exist to let someone at the party change the music.
What a guest cannot do is write to the library, touch configuration beyond player config, or manage
users.

**The service role exists for the Home Assistant integration.** It needs impersonation so a single
integration token can act on behalf of whichever user triggered an automation, and it needs to read
the user list, because impersonating a user is not useful without being able to enumerate them.

Reading users is a separate scope from managing them precisely because it is a far weaker
capability, and forcing every caller that needs to see users to hold full user management would be
wrong.

## Enforcement

Declaring a scope implies authentication, so a command cannot be scoped and anonymous. Enforcement
lives in exactly two places, one per transport, and they behave identically.

The user is set into context before the scope check, so a handler that needs a finer-grained rule
can read it and apply its own. Several commands do exactly that, for checks a decorator cannot
express: requiring a stronger scope only when the request targets somebody else, or accepting
either a scope or ownership of the relevant session.

Scopes are introspectable. A command returns the whole role-to-scope mapping so a frontend can grey
out actions it knows will fail, and the generated docs carry each command's requirement.

## Tokens

Tokens are signed, and the database stores only a hash, so a token can be revoked without ever
being stored. Revocation disconnects the holder immediately, as does disabling a user.

| Kind | Renewal | For |
|---|---|---|
| Short-lived | Renews on use against a sliding window, capped by an absolute lifetime | Interactive clients |
| Long-lived | None | Integrations and API access |
| Guest | None | Guest sessions |

Passwords are hashed with a salt combining the random user id and the server id, and failed logins
back off progressively.

## Ways in

First run with no users redirects to a setup route where the first administrator is created.

Under Home Assistant ingress there is no setup step at all: the request carries the user's identity
in headers, the account is created on first access, and no password is involved.

Standard login exchanges credentials for a token. The Home Assistant OAuth flow redirects for
consent and returns through a callback. **Remote clients use that same flow** rather than a separate
path; the return URL a client supplies is classified as trusted, external or blocked before a token
is appended to it, which is what makes the redirect safe across origins.

Note that "OAuth" covers two unrelated things here, and conflating them is the easiest mistake to
make. One is users authenticating *to* this server. The other is this server authenticating to a
music provider during its setup flow. They share no code.

## Join codes and guest access

A join code is a short, human-transcribable string exchanged for a token, and it is what backs QR
code and link-based guest entry.

The character set drops the glyphs people confuse when reading a code off a screen, and the length
is chosen so that an unauthenticated exchange endpoint is defensible on entropy alone.

**A code can only ever be issued for a guest account.** That single check is what stops the whole
mechanism from becoming a privilege-escalation path: even a leaked code yields a guest token.

The exchange endpoint has to be unauthenticated, since a joining guest has no credential yet, so it
is protected by a rate limiter, an exchange lock so concurrent attempts cannot all pass the check
before any failure is recorded, and expiry plus a use count.

The rate limiter has one subtlety worth preserving: its bucket key reports whether it identifies a
single caller exclusively, because a shared key must never be cleared by one client's success.
Otherwise a single legitimate guest would reset the budget an attacker is burning.

A shared helper packages the whole pattern so a plugin does not reimplement it, including creating
the guest account, which **refuses a username that already exists as a non-guest**, reusing an
active code, building the join URL, and revoking everything for that guest.

The join URL's form depends on reachability: with remote access enabled it works from anywhere,
otherwise it is LAN-only.

## Remote access

Remote access bridges WebRTC data channels to the local WebSocket API, so authentication and
authorization work exactly as they do locally and no port forwarding is needed.

An instance is identified by an id derived from its own certificate fingerprint rather than stored
separately. Two connection modes exist, one on public infrastructure and one using Home Assistant
Cloud relays for networks where a direct connection is impossible.

See [controllers/webserver/remote-access.md](../../music_assistant/controllers/webserver/remote-access.md).

## Related

- [events-and-commands.md](events-and-commands.md) for the registry and the event bus.
- [controllers/webserver](../../music_assistant/controllers/webserver/README.md) for the package.
- [configuration.md](configuration.md) for the config command surface.
- [ai-and-mcp.md](ai-and-mcp.md) for how an agent authenticates.

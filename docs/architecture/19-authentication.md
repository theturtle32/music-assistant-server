# 19 — Authentication and Authorization

Music Assistant authenticates every API caller and then authorizes each individual command against a **scope**. Authentication answers "who is this?" and lives in `AuthenticationManager` (`controllers/webserver/auth.py`, ~2420 lines) plus its login providers. Authorization answers "may they do this?" and is a per-command declaration enforced identically on both transports.

The two are deliberately separate. Roles exist, but nothing in the API checks a role directly — a role is only a named bundle of scopes, resolved through one mapping. That indirection is what made `SERVICE` accounts and future custom roles possible without touching a single command handler.

This document owns the model. [12-webserver-api.md](12-webserver-api.md) owns the transport that carries it: routes, dispatch, WebSocket lifecycle, and remote access.

---

## The scope model

### `Scope`

`Scope` is a `StrEnum` in `music_assistant_models.auth`. Twenty real scopes plus two special members — 22 in total:

| Scope | Value |
|---|---|
| `ALL` | `*` — grants everything; held only by `ADMIN` |
| `LIBRARY_READ` / `LIBRARY_WRITE` / `LIBRARY_MANAGE` | `library.read` / `library.write` / `library.manage` |
| `PLAYERS_READ` / `PLAYERS_CONTROL` | `players.read` / `players.control` |
| `QUEUES_READ` / `QUEUES_CONTROL` | `queues.read` / `queues.control` |
| `PROVIDERS_READ` | `providers.read` |
| `CONFIG_PLAYERS_READ` / `CONFIG_PLAYERS_WRITE` | `config.players.read` / `config.players.write` |
| `CONFIG_PROVIDERS_READ` / `CONFIG_PROVIDERS_WRITE` | `config.providers.read` / `config.providers.write` |
| `CONFIG_CORE_READ` / `CONFIG_CORE_WRITE` | `config.core.read` / `config.core.write` |
| `USERS_READ` / `USERS_MANAGE` / `USERS_IMPERSONATE` / `USERS_INVITE` | `users.read` / `users.manage` / `users.impersonate` / `users.invite` |
| `SYSTEM_READ` / `SYSTEM_MANAGE` | `system.read` / `system.manage` |
| `UNKNOWN` | `unknown` — **grants no access** |

`UNKNOWN` is a security default, not a placeholder. `Scope._missing_` returns it for any value the enum does not recognise, so a scope string from a newer server (or a typo in a stored value) deserializes into something that can never satisfy a check, rather than raising or matching by accident.

### Roles are a scope bundle

`ROLE_SCOPES` in `controllers/webserver/helpers/auth_middleware.py` maps a role id to a frozen scope set. Four built-in roles, defined cumulatively:

| Role | Scopes |
|---|---|
| `ADMIN` | `{Scope.ALL}` |
| `USER` | the guest set, plus `LIBRARY_WRITE`, `CONFIG_PROVIDERS_READ`, `CONFIG_CORE_READ`, `USERS_INVITE`, `SYSTEM_READ` |
| `GUEST` | `LIBRARY_READ`, `PLAYERS_READ`, `PLAYERS_CONTROL`, `QUEUES_READ`, `QUEUES_CONTROL`, `PROVIDERS_READ`, `CONFIG_PLAYERS_READ` |
| `SERVICE` | the user set, plus `CONFIG_PLAYERS_WRITE`, `USERS_READ` and `USERS_IMPERSONATE` |

Two design decisions in that table are worth drawing out.

**`GUEST` can control playback.** A guest gets `PLAYERS_CONTROL` and `QUEUES_CONTROL`, because the guest experiences MA supports — Party, Music Quiz, the dashboard viewer — are all about letting someone at the party actually change the music. What a guest cannot do is write to the library, read or write configuration beyond player config, or manage users.

**`SERVICE` exists for the Home Assistant integration.** It is a regular user plus exactly three things: player-config write (so HA can adjust player settings), `USERS_IMPERSONATE` (so a single integration token can act on behalf of whichever HA user triggered an automation) and `USERS_READ` (#5410 — impersonating a user is not useful without being able to *enumerate* them, which is what lets HA map its own users onto MA accounts). Pre-existing installs had this account on the plain `user` role; `_migrate_system_user_role()` moves it on startup.

**`USERS_READ` is separate from `USERS_MANAGE` for that reason.** Reading the user list is a far weaker capability than creating, editing or deleting accounts, so `auth/user` and `auth/users` gate on `USERS_READ` rather than forcing every caller that needs to *see* users to hold full user management.

`User.role` is typed as a plain `str`, not the `UserRole` enum, explicitly to leave room for custom roles. The consequence is fail-closed: a role id absent from `ROLE_SCOPES` resolves to an empty frozenset and therefore grants nothing.

### `has_scope`

The entire authorization check is four lines:

```python
def has_scope(user: User, scope: Scope) -> bool:
    role_scopes = ROLE_SCOPES.get(user.role, frozenset())
    return Scope.ALL in role_scopes or scope in role_scopes
```

There is no hierarchy, no wildcard matching on scope prefixes, and no per-user scope overrides. `Scope.ALL` is the only special case. A user either has the exact scope their role grants or they do not.

### Per-command enforcement

Commands declare their requirement in the `@api_command` decorator, and `APICommandHandler.required_scope` carries it:

```python
@api_command("config/providers/save", required_scope=Scope.CONFIG_PROVIDERS_WRITE)
async def save_provider_config(self, ...): ...
```

`required_scope=None` (the default) means "any authenticated user". Enforcement happens in exactly two places, and they behave identically:

| Transport | Location | Failure |
|---|---|---|
| WebSocket | `WebsocketClientHandler._handle_command` | `ErrorResultMessage` with `InsufficientPermissions.error_code` and the `insufficient_permissions` translation key |
| HTTP | `WebserverController._authenticate_api_command` | HTTP 403 with the scope name in the body |

Both gate on `handler.authenticated or handler.required_scope`, so declaring a scope implies authentication even if `authenticated=False` was passed. Both set the user into the context vars *before* the scope check, so a handler that does its own finer-grained check can read `get_current_user()`.

Scopes are also introspectable. `auth/scopes` returns the whole role→scope mapping (sorted, as plain strings) so a frontend can grey out actions it knows will fail, and the OpenAPI/commands generators emit `required_scope` per command — see [12-webserver-api.md](12-webserver-api.md#api-documentation).

Some commands need a check the decorator cannot express, and those do it inline with `has_scope`. `auth/token/create` requires `USERS_MANAGE` only when `user_id` targets somebody else; `dashboard/get_url` accepts either `USERS_INVITE` or a caller that owns a matching active dashboard session; `providers` filters music providers by the caller's `provider_filter` unless the caller holds `Scope.ALL`.

---

## Impersonation

The Home Assistant integration holds one token but serves many HA users. Rather than minting a token per user, MA lets a command run *as* another user.

A command opts in with `allow_impersonation=True`. The dispatch then pops a `user` argument (or the deprecated `username` alias) from the incoming args before parsing them, resolves it, and sets it as the impersonated user for that call:

```python
if handler.allow_impersonation and msg.args:
    if impersonation_user := await resolve_command_impersonation(self.mass, msg.args):
        set_impersonated_user(impersonation_user)
```

Several details make this safe and ergonomic:

- **`resolve_impersonated_user(mass, provider_type, provider_user_id, required=True)` resolves per auth provider** (#5417). A *builtin* user is looked up by user id or username, while a user belonging to another auth provider is resolved through their **provider link** — so an HA account can be named by its HA user id without MA having to mirror it as a local username. The command's `user` argument may therefore be a dict (`{provider, user_id, required}`) rather than a bare string, and `required=False` resolves to `None` instead of raising when the user cannot be found.
- **Self-impersonation is always allowed**; targeting *another* user requires `Scope.USERS_IMPERSONATE`, which only `ADMIN` (via `ALL`) and `SERVICE` hold. Failure raises `InsufficientPermissions`.
- **Empty values mean "no impersonation".** `None` and `""` are both treated as absent, because optional fields in HA automations and scripts commonly template to an empty string, and a blank template must not become an error.
- **`APICommandHandler.parse` refuses to register** a command that both allows impersonation and declares its own `user`/`username` parameter, since the dispatch would silently swallow the handler's argument. That is a `RuntimeError` at startup, not a runtime surprise.
- **`get_current_user()` returns the impersonated user when one is set**, falling back to the authenticated one. Handlers therefore need no impersonation awareness at all — they just ask who the current user is.

For server-internal code there is `ImpersonatedUser`, an async context manager. It exists for call paths that are not API commands (playback started by a hardware button, an external protocol without a user context) and is deliberately nestable: passing `None` is a no-op that preserves whatever impersonation is already active, and `__aexit__` restores the previous value rather than clearing it.

---

## Users

### The model

`User` (`music_assistant_models.auth`) is what both transports authenticate to:

| Field | Type | Notes |
|---|---|---|
| `user_id` | `str` | `secrets.token_urlsafe(32)` |
| `username` | `str` | Case-insensitive; normalized to lowercase for storage and lookup |
| `role` | `str` | A role id — see `UserRole` for the built-in values |
| `enabled` | `bool` | A disabled user cannot authenticate, and active sessions are dropped |
| `created_at` | `datetime` | |
| `display_name` | `str \| None` | |
| `avatar_url` | `str \| None` | |
| `preferences` | `dict` | Free-form client preferences |
| `provider_filter` | `list[str]` | Restrict visible **music** providers |
| `player_filter` | `list[str]` | Restrict visible players |

### Login providers

`BuiltinLoginProvider` — username and password. Passwords are hashed with `hashlib.pbkdf2_hmac("sha256", ..., iterations=100000)`, salted with `{user_id}:{server_id}`. Because `user_id` is a random 32-byte token and `server_id` is per-installation, the salt is unique per user *and* per install, so a hash is useless if lifted to another server.

A `LoginRateLimiter` tracks failed attempts per username over a rolling 30-minute window and imposes progressive delays:

| Failed attempts in window | Delay |
|---|---|
| 1–2 | none |
| 3–5 | 30 s |
| 6–9 | 60 s |
| 10–14 | 120 s |
| 15+ | 300 s |

`HomeAssistantOAuthProvider` — an OAuth2 flow, auto-enabled when the HA provider is configured. It uses HA's external URL for the authorization endpoint, exchanges the code for an HA token, reads the HA user id, and creates or links an MA user. An `allow_self_registration` setting controls whether an unknown HA user may create an MA account.

### First-run setup

Until a non-system user exists, the server is in setup mode and says so loudly in the log. Both transports refuse work: `POST /api` returns 503 "Setup required", the WebSocket sends a `setup_required` error and closes, and `POST /auth/login` returns 403. `GET /` redirects to `/setup`, where `POST /setup` creates the first admin (username ≥ 2 characters, password ≥ 8). Ingress skips all of this — HA has already authenticated the user, so the account is created on first access.

### Ingress auto-provisioning

Under the HA add-on, the ingress site (port 8094, bound to the internal `172.30.32.x` network) receives requests that HA has already authenticated, carrying `X-Remote-User-ID`, `X-Remote-User-Name`, and optionally `X-Remote-User-Display-Name`. Both `get_authenticated_user` (HTTP) and `WebsocketClientHandler._handle_ingress_auth` implement the same provisioning sequence:

1. Look for a user already linked to that HA user id through `AuthProviderType.HOME_ASSISTANT`.
2. Failing that, look for a user with the same username, and link it.
3. Failing that, create one — calling `get_ha_user_role()` to decide the role, and `get_ha_user_details()` for username, display name, and avatar.
4. On every subsequent request, refresh display name and avatar from HA. **HA is the source of truth**, with the ingress headers as fallback when the API lookup returns nothing.

`get_ha_user_role()` queries HA's `config/auth/list` (after waiting up to 10 s for the `hass` provider to become ready) and returns `UserRole.ADMIN` when the HA user's `group_ids` contain `system-admin`. So an HA administrator is an MA administrator, automatically.

The `X-Remote-User-ID` and `X-Remote-User-Name` headers are both **required**; a request missing either is not authenticated rather than partially trusted. Header trust is only extended because ingress itself is verified at the socket level — see [12-webserver-api.md](12-webserver-api.md#ingress-and-socket-level-verification).

### Multi-user filtering

Two per-user lists narrow what a user sees. They are **filters, not scopes** — they restrict *which objects*, where a scope restricts *which operations* — and they apply in different places:

| Filter | Where it applies |
|---|---|
| `player_filter` | API results, **and** the WebSocket event stream: player and queue events whose `object_id` is outside the filter are dropped per connection. Also checked by `handle_player_command` — see [04-player-controller.md](04-player-controller.md) |
| `provider_filter` | API results only — `mass.get_providers()` (`@api_command("providers")`), and the browse/library paths via `_apply_user_provider_filter` / `_ensure_provider_filter`. Also used as a *preference* when resolving which provider to stream a track from |

**`provider_filter` is not applied at the event layer.** Only `player_filter` is. A restricted user therefore still receives, say, provider-config events for providers they cannot browse; the filtering is a UI-scoping mechanism, not an isolation boundary. `mass.get_providers` skips `provider_filter` for a caller holding `Scope.ALL`, but browse/library helpers (`_ensure_provider_filter`, `_apply_user_provider_filter`) and WebSocket `player_filter` gating honor a non-empty filter even for an admin — `Scope.ALL` is not a universal bypass. See [08-media-library.md](08-media-library.md#provider-selection-and-user-filters).

---

## Token lifecycle

Tokens are **JWTs** signed HS256 with a per-installation secret held in the auth database's `settings` table. The payload carries `sub` (user id), `jti` (token id), `iat`, `exp`, plus `username`, `role`, `token_name`, and `is_long_lived`.

Only a **SHA-256 hash** of the issued token is stored, in `auth_tokens`. That is enough to revoke — delete the row — without the server ever holding a usable credential at rest. A pre-JWT hash-lookup path is retained for legacy tokens.

### The database is the source of truth

`authenticate_with_token` decodes the JWT, then re-reads the row and trusts *the row*, not the payload:

- if the row is missing → reject (this is how revocation works)
- if the payload's `sub` disagrees with the row's `user_id` → reject as tampered or stale
- if the row's `expires_at` has passed → delete the row and reject
- if the user is gone → reject

An expired signature is handled specially: the token id is extracted anyway and its row deleted, so an abandoned session cleans itself up rather than lingering until the daily sweep.

### Three token classes

| Class | Initial expiry | Renewal | JWT `exp` |
|---|---|---|---|
| Short-lived (session) | `TOKEN_SHORT_LIVED_EXPIRATION` = **30 days** | Sliding — extended 30 days on each use, but capped by `TOKEN_ABSOLUTE_MAX_EXPIRATION` = **90 days** from creation | set to the 90-day absolute cap |
| Long-lived (integration) | `TOKEN_LONG_LIVED_EXPIRATION` = **365 days** | **None** | same as the DB expiry |
| Guest | `TOKEN_GUEST_EXPIRATION` = **1 day** | **None** | same as the DB expiry |

Long-lived tokens last a year, not a decade, and never auto-renew. An integration must re-issue one annually.

The `exp` mismatch on short-lived tokens is deliberate and worth understanding: if `exp` carried the 30-day database expiry, JWT verification would reject the token on day 31 even though a sliding renewal had extended the row. Setting `exp` to the absolute cap lets the database own the sliding window while the signature still enforces a hard ceiling.

`_refresh_token_expiration` implements the renewal on every authenticated call, and does three things:

1. **Enforces the absolute cap.** A short-lived token older than 90 days is deleted and rejected, forcing genuine re-authentication regardless of activity.
2. **Throttles the write.** The HTTP API authenticates on every request, so persisting `last_used_at` per request would cost an `UPDATE` plus commit — an fsync — per request. The write is skipped while the stored timestamp is younger than `TOKEN_ACTIVITY_PERSIST_INTERVAL` (**1 hour**). Both `last_used_at` and the sliding expiry therefore lag by up to an hour, which is negligible against a 30-day idle window.
3. **Skips renewal for guests.** A guest token's expiry is never extended, so guest access really does end.

### Guests cannot hold long-lived tokens

`auth/token/create` rejects a guest target outright: "Long-lived tokens cannot be created for guest accounts". Combined with the fixed 1-day guest expiry and the no-renewal rule, this means guest access is bounded by construction rather than by an operator remembering to revoke it.

### Revocation and disconnect

`auth/token/revoke` deletes the row; a user may revoke their own tokens, and `USERS_MANAGE` is needed for anyone else's. Revocation is not just a database change — `webserver.disconnect_websockets_for_token(token_id)` walks live WebSocket clients and drops any whose `_token_id` matches, so an open session cannot outlive its credential.

Revoking a whole *user's* access is a separate path (#6133, #6134, #6135), because deleting or disabling an account has to close every session it holds rather than one token at a time. `AuthenticationManager.subscribe_user_access_revoked(callback)` is the notification hook, and `webserver.disconnect_websockets_for_user(user_id)` performs the disconnect — covering bulk revoke, disable and delete through one mechanism instead of each reimplementing the walk. A live change to a user's `player_filter` is applied to open connections without requiring a reconnect (#5785).

`auth/tokens` lists a user's tokens newest-first, capped at `TOKEN_LIST_LIMIT` (100).

`POST /auth/logout` is the self-service form: it hashes the bearer token from the request and deletes the matching row.

### The HA integration token

The integration's token is stored server-side under `ha_integration_token` and reused across restarts rather than re-minted, so MA can re-announce it to the Supervisor. It is the one token kept in **plaintext** rather than as a hash, with an explicit rationale in the code: the JWT secret sits in the same `settings` table and can mint any token anyway, so hashing this one would buy nothing.

`_can_reuse_ha_integration_token` validates it and additionally rotates proactively: reuse stops once the token is within `HA_TOKEN_ROTATION_MARGIN` (**7 days**) of the 90-day absolute cap, so rotation happens on MA's schedule rather than at the moment the integration breaks. A superseded token stays valid until its own expiry, so HA keeps working until it next reloads.

---

## Join codes and guest access

A join code is a short, human-transcribable string exchanged for a token — the mechanism behind QR-code and link-based guest entry.

| Constant | Value |
|---|---|
| `JOIN_CODE_LENGTH` | **12** |
| `JOIN_CODE_CHARSET` | `ABCDEFGHJKLMNPQRSTUVWXYZ23456789` — no `I`, `O`, `0`, or `1` |
| `JOIN_CODE_DEFAULT_EXPIRY_HOURS` | **8** |

The charset drops the four glyphs people confuse when reading a code off a screen or a printed card. Twelve characters from a 32-symbol alphabet is 60 bits of entropy, which is what makes an unauthenticated exchange endpoint defensible.

`generate_join_code` refuses to issue a code for anything but a `GUEST` account. That single check is what stops the whole join-code mechanism from ever becoming a privilege-escalation path: even if a code leaks, the token it yields belongs to a guest.

`auth/join_code/exchange` is `authenticated=False` by necessity — a joining guest has no credential yet. It is protected instead by:

- a **rate limiter** (`_join_code_rate_limiter`, the same `LoginRateLimiter` class) whose bucket is chosen by `_join_code_rate_limit_key()` (#5243): the WebSocket `client_id` when there is one, else `peer:{address}` from [`current_peer_address`](#context-variables), else a shared anonymous key. The function returns a second value saying whether the key identifies **one caller exclusively**, because a shared key must never be cleared by one client's successful exchange — otherwise a single legitimate guest would reset the budget an attacker is burning. A separate global ceiling still bounds total failures
- an **exchange lock**, so concurrent attempts cannot all pass the rate-limit check before any failure is recorded
- **expiry and use count** — `max_uses` of 0 means unlimited, and exhausted or expired codes are swept daily

### The shared guest-access helper

`helpers/guest_access.py` packages the whole pattern so a plugin does not reimplement it:

| Function | Purpose |
|---|---|
| `get_or_create_guest_user(mass, username, display_name)` | Fetch or create a dedicated guest account. **Raises if the username exists as a non-guest** — the guard that prevents handing out guest access on a privileged account |
| `get_or_create_join_code(mass, user, ...)` | Reuse the active code for that guest if there is one, else generate |
| `build_join_url(mass, code)` | The URL a guest opens |
| `revoke_guest_access(mass, username)` | Revoke every code and token for the guest, disconnecting live sessions |

`build_join_url` picks its form from remote-access state: with remote access enabled it returns `https://app.music-assistant.io/?remote_id=<remote-id>&join=<code>`, which works from anywhere over WebRTC; otherwise it returns `<base_url>/?join=<code>`, which only works on the LAN.

Three consumers use this today: the **Party** plugin (`party_guest`), **Music Quiz**, and the **dashboard** controller, whose `dashboard_viewer` guest account backs a 1-hour code embedded in cast dashboard URLs. See [11-plugin-system.md](11-plugin-system.md#shared-playback-sessions) and [12-webserver-api.md](12-webserver-api.md#dashboard).

---

## OAuth: two unrelated flows

The word "OAuth" covers two things in MA that share no code and solve different problems. Conflating them is the easiest mistake to make here.

### Webserver login OAuth

This is a *login provider*: `HomeAssistantOAuthProvider`, reached through `GET /auth/authorize` → HA consent → `GET /auth/callback`. It ends with an MA token handed back to the client.

The token is delivered by redirecting to a `return_url` with the token appended as a `code` query parameter, which makes `return_url` validation a security boundary. `helpers/redirect_validation.py` classifies every candidate into one of three buckets:

| Category | Meaning |
|---|---|
| `trusted` | Auto-allowed: same origin as the request, localhost, an RFC 1918 private IP, the configured `base_url`, or a registered pattern (`musicassistant://`, `my.home-assistant.io`, `homeassistant.local`) |
| `external` | Valid, but requires explicit user consent |
| `blocked` | Rejected — empty, no hostname, or a scheme other than http/https and the registered custom schemes |

`build_code_redirect_url` then appends the code **before any hash fragment**, so it lands in the query string where the client can read it rather than being swallowed by the fragment.

There is **no polling flow and no pending-session concept** here: a provider OAuth popup and webserver authentication are unrelated mechanisms that happen to share the word "auth". The `AUTH_SESSION` event member still exists in the enum but nothing emits it — see [01-event-system.md](01-event-system.md#members-present-but-never-emitted).

### Provider setup-flow OAuth

This is not login at all. It is how a *music provider* obtains its own credentials during setup, and it lives in `helpers/oauth.py`.

The problem it solves: providers like Spotify, Google, and Microsoft only accept **pre-registered** redirect URIs, and MA's callback URL is per-installation and per-session, so it can never be registered. The fix is a hosted bounce. `hosted_bounce_redirect(callback_url)` returns the fixed, pre-registered `HOSTED_CALLBACK_URL` (`https://music-assistant.io/callback`) as the `redirect_uri`, and smuggles the session's real local callback URL through the `state` parameter. The hosted page reads `state` and forwards the browser to the local callback.

`authorization_code_from_params` extracts the code and knows one wart of that relay: on denied consent the hosted page forwards the literal string `"null"`, so it is rejected alongside a genuinely missing code. See [02-configuration.md](02-configuration.md#setup-flows) for the setup-flow engine this plugs into.

---

## Context variables

Authentication state reaches deep call chains through `contextvars.ContextVar` rather than being threaded as parameters. Six vars, each with a getter and setter in `auth_middleware.py`:

| Variable | Getter | Carries |
|---|---|---|
| `current_user` | `get_current_user()` | The authenticated user — **but see below** |
| `current_token` | `get_current_token()` | The raw bearer token, for self-revocation |
| `impersonated_user` | `get_impersonated_user()` | The user this call is acting as, if any |
| `sendspin_player_id` | `get_sendspin_player_id()` | The Sendspin player bound to this connection |
| `current_client_id` | `get_current_client_id()` | The WebSocket connection id — `None` outside a WebSocket command |
| `current_peer_address` | `get_current_peer_address()` | The network address a stateless API request came from |

`get_current_user()` deliberately returns the **impersonated** user when one is set, and only falls back to `current_user.get()` otherwise. This is the single point that makes impersonation transparent: a handler asking "who is the current user?" gets the effective answer without knowing impersonation exists. Code that specifically needs the *authenticated* identity — as `resolve_impersonated_user` does when checking whether the caller may impersonate — reads `current_user` directly.

`current_client_id` is what lets a command know which WebSocket connection invoked it, used by the dashboard controller to tie a registration to a connection so it can be dropped when that connection closes.

`current_peer_address` is set by the webserver from `request.remote` and exists for rate limiting stateless requests. Its docstring is careful about how much it is worth: a reverse proxy or Home Assistant Ingress presents *its own* address for every client behind it, so it identifies a caller far less precisely than a client id does — which is why the join-code limiter prefers `client_id` and only falls back to the peer address.

---

## Auth database

A dedicated SQLite database, `auth.db`, at schema version **5**. Five tables:

| Table | Contents |
|---|---|
| `settings` | Key/value: schema version, JWT secret, the plaintext HA integration token |
| `users` | User accounts |
| `user_auth_providers` | Links a user to a login provider (builtin password hash, HA user id) |
| `auth_tokens` | Token id, user id, SHA-256 hash, name, created/expires/last-used, long-lived flag |
| `join_codes` | Code, guest user, expiry, use count, device name |

Keeping this separate from `library.db` means a library restore or wipe does not affect credentials, and vice versa.

---

## Security posture summary

| Concern | Mechanism |
|---|---|
| Password storage | PBKDF2-HMAC-SHA256, 100k iterations, salted per user *and* per install |
| Token storage | Only a SHA-256 hash persisted; the database is authoritative for expiry so revocation is immediate |
| Brute force | Progressive per-username delays over a 30-minute window; a separate global limiter plus a lock on join-code exchange |
| Unknown scope values | `Scope.UNKNOWN` — matches nothing |
| Unknown role ids | Empty scope set — grants nothing |
| Session longevity | 90-day absolute cap on sliding sessions; 1-day non-renewable guest tokens; long-lived tokens blocked for guests |
| Live session revocation | WebSocket disconnect on token revocation or user disable |
| Ingress header trust | Socket-level verification of the ingress bind address and port before any header is read |
| HA system user | Rejected on the regular webserver; usable only over ingress |
| Redirect abuse | Three-way `trusted`/`external`/`blocked` classification before a token is appended to any `return_url` |

---

## Key Files

| File | Purpose |
|---|---|
| `music_assistant_models.auth` | `Scope`, `UserRole`, `User`, `AuthToken`, `UserAuthProvider`, `AuthProviderType` |
| [`music_assistant/controllers/webserver/auth.py`](../../music_assistant/controllers/webserver/auth.py) | `AuthenticationManager` — users, tokens, join codes, the `auth/*` command surface, token refresh and rotation |
| [`music_assistant/controllers/webserver/helpers/auth_middleware.py`](../../music_assistant/controllers/webserver/helpers/auth_middleware.py) | `ROLE_SCOPES`, `has_scope`, impersonation resolution, `ImpersonatedUser`, the context vars, ingress detection, `get_authenticated_user`. The `auth_middleware` / `require_authentication` functions the module is named after were deleted in #5211 |
| [`music_assistant/controllers/webserver/helpers/auth_providers.py`](../../music_assistant/controllers/webserver/helpers/auth_providers.py) | `BuiltinLoginProvider`, `HomeAssistantOAuthProvider`, `LoginRateLimiter`, `get_ha_user_role`, `get_ha_user_details` |
| [`music_assistant/helpers/jwt_auth.py`](../../music_assistant/helpers/jwt_auth.py) | `JWTHelper` — HS256 encode/decode, claim layout, token-id extraction |
| [`music_assistant/helpers/guest_access.py`](../../music_assistant/helpers/guest_access.py) | Shared guest user, join code, join URL, and revocation helpers |
| [`music_assistant/helpers/redirect_validation.py`](../../music_assistant/helpers/redirect_validation.py) | `is_allowed_redirect_url`, `build_code_redirect_url` |
| [`music_assistant/helpers/oauth.py`](../../music_assistant/helpers/oauth.py) | Provider setup-flow OAuth hosted bounce — unrelated to webserver login |
| [`music_assistant/helpers/api.py`](../../music_assistant/helpers/api.py) | `@api_command`, `APICommandHandler` — where `required_scope` and `allow_impersonation` are declared |
| [`music_assistant/controllers/webserver/websocket_client.py`](../../music_assistant/controllers/webserver/websocket_client.py) | WebSocket-side scope enforcement, impersonation, event filtering |
| [`music_assistant/controllers/webserver/controller.py`](../../music_assistant/controllers/webserver/controller.py) | `_authenticate_api_command`, the `/auth/*` and `/setup` HTTP handlers, `disconnect_websockets_for_token` |

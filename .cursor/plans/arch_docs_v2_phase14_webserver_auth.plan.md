---
name: arch_docs_v2_phase14_webserver_auth
overview: Phase 14. Correct the transport-layer drift in 12-webserver-api.md (routes, dispatch, tokens, join codes, Remote ID, WebRTC library, dynamic routes, dashboard namespace) and create a new 19-authentication.md for the scope-based authorization model, roles, impersonation, guest access, and token lifecycle that replaced role strings.
todos:
  - id: preflight
    content: "Pre-flight: verify routes, the api_command decorator, dispatch, token constants, and the Scope model against the working tree"
    status: completed
  - id: routes
    content: "12-webserver-api.md: fix the route map and architecture diagram (dynamic imageproxy, added auth/static routes, per-file frontend registration, CORS)"
    status: completed
  - id: dispatch
    content: "12-webserver-api.md: fix the api_command decorator, APICommandHandler dataclass, dispatch flow, and the _register_api_commands scan list"
    status: completed
  - id: websocket
    content: "12-webserver-api.md: fix WebSocket heartbeat, event subscription filtering, and the special pre-dispatch commands"
    status: completed
  - id: remote
    content: "12-webserver-api.md: fix the Remote ID derivation and format, the WebRTC library, and remote access scopes"
    status: completed
  - id: newsurfaces
    content: "12-webserver-api.md: add dynamic routes, the dashboard API namespace, diagnostics command, providers/icon, and an MCP cross-link"
    status: completed
  - id: newdoc_scopes
    content: Create docs/architecture/19-authentication.md with the Scope model, roles, and per-command enforcement
    status: completed
  - id: newdoc_tokens
    content: "19-authentication.md: token lifecycle, join codes, guest access, and OAuth security"
    status: completed
  - id: newdoc_users
    content: "19-authentication.md: users, impersonation, provider filters, and ingress auto-provisioning"
    status: completed
  - id: crosslinks
    content: Add auth cross-links from the docs that reference required_role or admin-only commands
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 14 — Webserver API and authentication

Files: `docs/architecture/12-webserver-api.md` (40–60% rewrite) and a new
`docs/architecture/19-authentication.md`.

Authentication earns its own file: it now spans ~1500 lines in `webserver/auth.py`, scope
enforcement in every controller, guest access helpers, join codes, JWT lifecycle, impersonation, and
four roles. `12-webserver-api.md` stays focused on transport — HTTP and WebSocket routes, dispatch,
remote access, static frontend.

Related in-tree README: `music_assistant/controllers/webserver/README.md`. Note it had its own
errors (bcrypt vs PBKDF2, stale Remote ID format); Phase 1 fixes those, so cross-check consistency.

## `12-webserver-api.md`

### Routes

- `/imageproxy` is no longer a static query-string route. `MetaDataController.post_setup()`
  registers the **dynamic** `/imageproxy/{image_id}?size=&fmt=` on both the webserver and streams
  controllers; the legacy endpoint was removed in #4544. Cross-link Phase 11.
- Missing routes: `POST /auth/logout`, `PATCH /auth/me`, `GET /logo.png`,
  `GET /resources/common.css`, the static `/assets/` mount, and CORS `OPTIONS` on `/info` and
  `/auth/login`.
- Frontend files are registered **individually** from `locate_frontend()`, not served by a single
  `GET /{filename}` catch-all.
- Add **dynamic routes** as a concept: `Webserver(..., enable_dynamic_routes=True)` and
  `register_dynamic_route`.

### Command dispatch

- The `@api_command` third attribute is **not** `required_role`. It is scope-based (#4613):

```python
@api_command(
    "players/all",
    authenticated=True,
    required_scope=Scope.PLAYERS_READ,
    allow_impersonation=False,
    alias=False,
)
```

  The decorator sets `api_required_scope`, `api_allow_impersonation`, and `api_alias`.
- `APICommandHandler` fields: `required_scope: Scope | None`, `allow_impersonation: bool`,
  `alias: bool` — not `required_role: str | None`.
- The dispatch flow checks **scope** via `has_scope()` and optionally resolves a `user`
  impersonation argument when `allow_impersonation=True` (targeting another user requires
  `Scope.USERS_IMPERSONATE`). Enforcement lives in `websocket_client.py` and
  `controller.py::_authenticate_api_command`.
- `_register_api_commands` also scans `translations`, `streams.audio_analysis`, `diagnostics`, and
  `dashboard`. Keep this list in sync with Phase 2's startup-order edits.

### WebSocket

- Heartbeat is `heartbeat=25`, not 30 seconds.
- Event subscription also filters `SETUP_FLOW_UPDATED` by the flow's required scope (or by both
  `CONFIG_PROVIDERS_WRITE` and `CONFIG_PLAYERS_WRITE` when the flow is gone). Note that
  `provider_filter` is **not** applied at the event layer — it filters API results.
- Ingress connections auto-authenticate and subscribe immediately; regular connections subscribe
  only after a successful `auth` command.
- `translations/set_locale` is handled as a special pre-dispatch command alongside `auth`.

### Remote access

- **Remote ID:** not `MA-XXXX-XXXX`. It is a 26-character uppercase alphanumeric string derived from
  the SHA-256 fingerprint of the persistent WebRTC DTLS certificate
  (`helpers/webrtc_certificate.py::_remote_id_from_certificate`), available even when remote access
  is disabled. Tests assert the 26-character length. Some upstream UI copy still shows the old
  format — call that out as stale rather than repeating it.
- The certificate lives in `$HOME/.musicassistant/` as `webrtc_certificate.pem` /
  `webrtc_private_key.pem`.
- The WebRTC stack is **`aiolibdatachannel`** (libdatachannel), not aiortc (#4930), lazily loaded
  only when remote access is enabled (#4292).
- `remote_access/info` and `remote_access/configure` require `Scope.SYSTEM_MANAGE`, not a bare admin
  check.

### New API surfaces

- **Dashboard** (#4887): `dashboard/*` API commands with guest viewer codes and a WebSocket
  `client_id` requirement. It has **no HTTP routes**, so it belongs in the API namespace list here
  rather than in its own doc.
- **Diagnostics** (#4652): `diagnostics/get` requiring `Scope.SYSTEM_MANAGE`. The HTTP download
  endpoint was removed (#4709). One line here; Phase 16 owns the detail.
- **`providers/icon`** (#4907): on-demand base64 provider icons.
- **MCP:** the FastMCP server mounts at `/mcp/v1` — one paragraph plus a cross-link to
  `18-ai-and-mcp.md` (Phase 13).

### Key files

Cross-reference `helpers/jwt_auth.py`, `helpers/guest_access.py`, `helpers/oauth.py`,
`helpers/redirect_validation.py`, `helpers/webrtc_certificate.py`, `controllers/webserver/README.md`,
and the SSL helper. Note that `music_assistant/helpers/auth.py` was **deleted** (#5030) — it was
`AuthenticationHelper` for provider OAuth popups, not webserver auth, so don't conflate them.

The doc's PBKDF2 claim is correct (`auth_providers.py` uses `hashlib.pbkdf2_hmac`) — keep it. Do not
"fix" it toward the in-tree README's incorrect bcrypt claim.

## New file: `docs/architecture/19-authentication.md`

Cover:

- **Scope model:** the `Scope` enum, `ROLE_SCOPES` in `auth_middleware.py`, `has_scope()`,
  per-command `required_scope`, the `auth/scopes` API command returning the role→scope mapping, and
  the `required_scope` field in the OpenAPI output. Admin is `Scope.ALL`.
- **Roles:** four built-in roles — `ADMIN`, `USER`, `GUEST`, and **`SERVICE`** (the Home Assistant
  integration system user, migrated from the old `user` role). Make clear that authorization is
  scope-derived, so user management requires `Scope.USERS_MANAGE` rather than a role equality check.
- **Impersonation:** `allow_impersonation`, `resolve_command_impersonation`, the `ImpersonatedUser`
  context manager, and the HA integration use case.
- **Token lifecycle:** `TOKEN_LONG_LIVED_EXPIRATION = 365` days (not ~10 years, and no
  auto-renewal); short-lived tokens sliding 30 days but capped by
  `TOKEN_ABSOLUTE_MAX_EXPIRATION = 90` days from creation; `last_used_at` persisted at most hourly
  (`TOKEN_ACTIVITY_PERSIST_INTERVAL`); guest tokens `TOKEN_GUEST_EXPIRATION = 1` day with no
  renewal, and long-lived tokens blocked for guests (#4556, #4661).
- **Join codes:** `JOIN_CODE_LENGTH = 12` (not 6), charset `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`,
  rate-limited on exchange via `_join_code_rate_limiter` (#4558). Shared through
  `helpers/guest_access.py` for Party, dashboard viewer tokens, and other guest experiences (#4672).
- **Guest access:** guest users, join URLs including the remote ID, and revocation.
- **OAuth security:** `helpers/oauth.py` hosted bounce (`HOSTED_CALLBACK_URL` via
  music-assistant.io) for **provider setup flows** — distinct from webserver login — and
  `helpers/redirect_validation.py` validating `return_url` before appending a token (#4649, #4272).
  Note that the `auth/oauth_status` polling mechanism was removed (#5030) and should not be
  documented.
- **Context variables:** `get_current_user`, `get_current_token`, `get_sendspin_player_id`, plus
  `impersonated_user` / `get_impersonated_user` and `current_client_id` / `get_current_client_id`.
- **Ingress:** auto-creates users from HA headers, assigns a role via `get_ha_user_role()` (HA admin
  → MA admin), fetches display name and avatar from the HA API, and links the provider on first
  access.
- **Multi-user filtering:** what `provider_filter` does and where it applies (API results, not
  events), cross-linking Phase 10.

## Cross-links

Sweep for `required_role` and "admin-only" claims across the docs tree and point them at
`19-authentication.md`. Phases 2, 3, 4, 10, and 15 each leave a scope cross-link expecting this file
to exist.

## Verification

- `rg "required_scope|api_required_scope|ROLE_SCOPES|has_scope|USERS_IMPERSONATE|TOKEN_ABSOLUTE_MAX_EXPIRATION|JOIN_CODE_LENGTH"`.
- `rg "required_role"` — should find nothing in `music_assistant/`.
- Confirm the Remote ID length assertion in `tests/helpers/test_webrtc_certificate.py`.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): webserver transport fixes and new authentication doc

Phase 14 of the upstream/dev refresh.
```

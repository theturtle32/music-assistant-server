# Permissions and authentication

Part of the [MCP server plugin](README.md).

## Visibility is operator-driven, not scope-driven

Every tool, resource and prompt is tagged, and each tag maps one-to-one onto a provider config
boolean. Middleware then applies one rule everywhere:

- A component with at least one enabled tag is exposed.
- A component with no tags is exposed, which covers always-on infrastructure.
- A component whose tags are all disabled is hidden.

The distinction from the MCP library's own tag restriction matters. That is scope-based
authorization, where the token must carry a scope. This is **operator-driven visibility**: flip a
boolean and the tools disappear from listings entirely, with no error path and no permission-denied
trace for the model to reason about.

Listings are filtered after the fact, and calls re-check by name or URI, so a client that cached a
tool name from an earlier permission set cannot reach a now-disabled tool. An unknown component is
rejected as not-found rather than as a server error, and the error class is chosen per component
kind so the SDK reports the failure under the right method.

**All debug and config flags are off by default**, which is the right posture for tools that can
read logs or write secrets.

## Confirmation for destructive calls

A destructive operation can additionally require interactive confirmation, which asks the client to
elicit a yes or no and raises on decline.

Its fallback logic is deliberately asymmetric. A client with no elicitation support at all passes
through, since the permission flag remains the primary defence. But any other wire error fails
closed, so a client whose handler throws can never silently confirm a destructive call.

## Authentication

Authentication is optional. When on, the token verifier delegates to the server's own
authentication, which already handles every token form. **The plugin implements no token decoding
or scope checking of its own**, because duplicating that would create two sources of truth.

The one thing it does decode itself is the audience claim, for audience binding, and the ordering
is a security decision. The audience check runs **before** delegating, because delegating refreshes
the sliding-window token expiry. Verifying first would let a stolen non-MCP token be kept alive
indefinitely by hitting the MCP endpoint.

Enforcement has a strict mode, which rejects a missing or mismatched audience and therefore also
rejects legacy tokens with no claim to inspect, and a soft mode that only warns, so operators can
migrate gradually.

When authentication is on and a public base URL is known, a sibling route publishes the
protected-resource metadata document that the MCP layer advertises on an unauthorized response, so
spec-compliant clients can discover the authorization server. Its supported scopes are supplied
lazily, so a hot-swapped permission change is reflected immediately.

Token mechanics, scopes and the wider route map belong to
[controllers/webserver](../../controllers/webserver/README.md); this plugin owns only the MCP-facing
shape.

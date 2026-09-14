# MCP server plugin

Publishes Music Assistant as a Model Context Protocol server, so an external agent can drive it.
This is the opposite direction from the AI provider features, where Music Assistant calls a model;
see [ai and mcp](../../../docs/architecture/ai-and-mcp.md) for both halves.

**The constraint that shapes everything: no second server.** The runtime mounts into the existing
webserver under a configurable path. No extra server process, no extra port, no changes to core.

## Deep dives

- [Permissions and authentication](permissions.md): tag-driven visibility, confirmation, and
  authentication.

## Module layout

| Module | Role |
|---|---|
| `provider.py` | The provider: lifecycle, config, hot-swap versus restart |
| `server.py` | Builds the MCP root and mounts the namespaced sub-servers |
| `http_bridge.py` | Translates an aiohttp request into ASGI and back |
| `middleware.py` | Tag-based visibility filtering |
| `auth.py` | Token verification delegated to the server's own auth |
| `origins.py` | The origin allowlist |
| `meta_discovery.py` | Optional meta-tools that replace the full catalog listing |
| `tools/`, `resources`, `prompts.py` | The published surface |
| `connect/` | The onboarding wizard |
| `tags.py`, `config.py`, `models.py` | Tag definitions, config mapping, response shapes |

## The ASGI bridge

The MCP library exposes a Starlette-based ASGI app; this server is aiohttp. The bridge translates a
single request into ASGI events and back into a streaming response, registered as a dynamic route.

Four details in there are load-bearing.

**Streaming passes through verbatim.** Server-sent events and chunked responses are not buffered,
so keep-alive heartbeats and tool progress reach the client live.

**The ASGI lifespan is driven explicitly.** Without sending the startup event the session manager
never enters its task group and the very first request fails outright. Unmounting awaits the
shutdown rather than firing a task, so a restart cannot begin while the previous session manager's
task group is still draining.

**The library is told its own mount path** rather than having a prefix stripped in the bridge. With
a strip it would receive a bare root path and its internal router would reject everything.

**Origin is checked before anything else.** The allowlist derives from loopback, the configured
base URL and the published IP, extended by a configurable list for reverse-proxy hostnames and
ingress. A disallowed origin is refused before reaching the MCP layer at all, which is
DNS-rebinding defence for a local-network server.

## The tool surface

Namespaced sub-servers are mounted onto the root, so tool names read as namespace and tool. The
namespaces cover the library, the queue, playback, players, playlists, media, metadata, debugging
and configuration.

How many tools a given client sees depends entirely on configuration; see
[Permissions and authentication](permissions.md).

Every tool carries annotations describing whether it is read-only, destructive, idempotent or
open-world, plus a title, so a host can present risk sensibly. Timeouts are chosen per cost class,
from local calls through provider-reaching queries to bulk playlist edits.

**Responses are deliberately not this project's wire models.** Purpose-built brief and result
shapes keep tool output small enough to be worth a model's context budget. A lean schema option
shrinks the admin namespaces further for hosts that eagerly load everything.

## Resources and prompts

Two optional layers, each behind its own toggle.

Resources expose URI-addressable read-only views of library items, players and queues. They are
tagged like tools and filtered by the same middleware.

Prompts are canned playbooks that hand a model an opinionated tool-chaining recipe, so it does not
re-derive the workflow each session. They encode hard-won operational detail: stop rather than
retry when a search comes back empty, read the queue's insertable index instead of trusting array
position, and a synced player's active queue lives under the group's id rather than its own.

## Meta-tool discovery

Hosts that load every tool schema up front pay a large token cost per session. With meta-discovery
on, the listing collapses to three meta-tools: a ranked search returning names and descriptions,
one full schema on demand, and a call proxy. Hosts that already defer schemas should leave it off.

The permission story here is deliberate: rather than reimplementing checks, this layer routes
through the existing ones. The search catalog is fetched with middleware enabled so it is filtered,
the proxy re-enters the normal call path, and schema fetches re-check visibility. Catalogued tools
stay directly callable while hidden from the listing, so a stale client keeps working and stays
gated.

## Reconfiguration

Changed keys are compared against the hot-swappable set, which covers the permission flags, the
resource toggles and the meta-discovery flag. A subset of those just replaces the tag set the
middleware reads, so new permissions apply on the next request with no remount.

Anything else tears the runtime down and rebuilds it, including the lean schema option, which is
read at build time, and the mount path. A resource toggle also forces a full restart, because
resource registration is decided at start time.

Rebuild safety is handled at both ends. Starting rolls back through the stop path on any partial
mount failure, so a retry cannot accumulate orphaned well-known routes or zombie ASGI lifespans.

## The connect wizard

Onboarding a client by hand means minting a token, finding the endpoint URL and hand-editing a
config file. The wizard replaces that with a single page that mints a per-client long-lived token
and renders ready-to-paste snippets, deeplinks and share URLs for the common MCP hosts. A config
action opens it from the provider's settings page.

Its mount failure is explicitly **non-fatal**, logged as a warning with the MCP server itself
unaffected, because losing an onboarding convenience should not take down the endpoint.

## Related architecture docs

- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for both directions of AI integration.
- [API and auth](../../../docs/architecture/api-and-auth.md) for tokens, scopes and the route map.
- [Providers](../../../docs/architecture/providers.md) for the plugin provider lifecycle.

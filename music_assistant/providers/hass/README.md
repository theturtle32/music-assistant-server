# Home Assistant

The single connection to a Home Assistant instance, and the foundation several other things stand
on. It maintains the WebSocket connection to HA, and the Music Assistant integration inside HA
relays its own API traffic back over that same connection rather than opening a second one.

It is a plugin rather than a player provider. Using HA media players as Music Assistant players is
a separate provider that depends on this one.

## Features are computed, not declared

Nearly every provider declares a fixed feature set. This one does not: it adds and removes the
speech and query features at runtime, depending on what the connected HA instance currently
exposes.

Each matching HA entity becomes a selectable **engine** rather than the provider being selected as
a whole, which is what lets one HA instance offer several voices or several models. See
[ai and mcp](../../../docs/architecture/ai-and-mcp.md) for the engine model and why substituting a
different engine for a missing one is never allowed.

Entities come and go without this provider loading or unloading, so a change in the entity set
signals consumers that their stored selection may need re-evaluating. Anything reading these
engines therefore has to handle the set changing underneath it, and re-read rather than cache.

## Entities as player controls

HA entities can also act as power, volume and mute controls for players that have none of their
own, or whose own controls the user would rather not use. This provider keeps the searchable
listing of eligible entities that the player config offers.

That is the concrete backing for one branch of the control chain described in
[players](../../../docs/architecture/players.md): "delegated to an external control entity" means
an entity served from here.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the plugin categories.
- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for the speech and query features and the
  engine contract.
- [Players](../../../docs/architecture/players.md) for control chains and announcements.
- [API and auth](../../../docs/architecture/api-and-auth.md) for the service role and the
  integration token this connection carries.

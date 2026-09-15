# Discovery controller

Owns network discovery: the shared Zeroconf instance and its interface selection, mDNS browsing
for provider-declared subscriptions, SSDP search cycles, and advertising the Music Assistant
server itself.

## Deep dives

- [mDNS discovery](mdns.md): the aggregated browser, replay, on-demand lookup and exact name
  matching.

## Responsibilities

- Build one shared Zeroconf browser covering every service type any manifest declares.
- Run SSDP discovery periodically for active providers and fan results out through callbacks.
- Replay cached mDNS results when a provider loads, so it does not wait for the next announcement.
- Register and unregister the server's own Zeroconf service.

## Provider integration

Providers opt in from `manifest.json` and implement the matching callback on their provider class:

| Manifest key | Declares | Provider implements |
|---|---|---|
| `mdns_discovery` | Zeroconf service types | The mDNS service state change callback |
| `upnp_discovery` | SSDP search targets | The UPnP service discovered callback |

Subscription is a capability of any provider, not only player providers.

Player providers can still keep their own discovery entry point for paths that shared network
discovery does not cover, such as manual IP configuration or a controller-side refresh.

## Why one shared instance

Running a Zeroconf instance per provider would mean several browsers on the same service types,
duplicated network traffic and several lifecycles to coordinate. One instance, one browser and
per-provider callback routing keeps that to a single subscription regardless of how many providers
care about a given service type.

Interface selection lives here for the same reason: the choice has to be made once, and every
consumer inherits it.

## Server advertisement

The server advertises itself over Zeroconf so clients can find it without configuration. A host
with several addresses advertises them all, because a client may be reachable on only one of them.

## Related architecture docs

- [Discovery](../../../docs/architecture/discovery.md) for the big picture and the provider matrix.
- [Providers](../../../docs/architecture/providers.md) for manifests and the provider lifecycle.

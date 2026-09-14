# Yandex Smart Home

Exposes Music Assistant players as Yandex Smart Home devices, so Alice can control playback by
voice. Playlists are exposed as device sources.

Architecturally it is the **mirror image of a receiver**: commands flow in from an external service
and are translated into player commands, and no audio crosses the boundary in either direction. It
declares no provider features, because none of the existing ones describe what it does.

Voice skills proper are a separate provider. This one covers smart-home device control only.

## Three ways to be reachable

The awkward part of this integration is not the device model, it is getting Yandex's servers to
reach a server sitting behind a home router. Three modes trade setup effort against isolation.

| Mode | How Yandex reaches the server | Cost |
|---|---|---|
| Cloud | Through a public community relay | No setup, but the public skill links to one instance per Yandex account |
| Cloud plus | Through the same relay, behind a private skill | Several instances per account, but the skill is registered by hand in Yandex's developer console |
| Direct | Yandex calls the server's webserver | No relay, but requires the server to be reachable over public HTTPS |

Most installs cannot do direct, which is why the relay modes exist at all rather than being a
convenience.

Authentication and provisioning are handled in the setup flow, so only genuine playback options
appear as config entries. That split is the general rule for anything interactive; see
[configuration](../../../docs/architecture/configuration.md).

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the plugin categories and the bridge pattern.
- [Players](../../../docs/architecture/players.md) for the commands it translates into.
- [Configuration](../../../docs/architecture/configuration.md) for setup flows versus config
  entries.

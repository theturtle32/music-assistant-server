# Sendspin

The native playback protocol, implementing the
[Sendspin Audio Protocol](https://github.com/Sendspin/spec) developed by the Open Home Foundation.
It gives sample-accurate synchronized playback across clients, per-player processing, live metadata
and bidirectional control, without depending on any vendor's ecosystem.

This provider owns client connections and output players. Audio captured *by* a source-role client
is exposed by the separate [sendspin_source](../sendspin_source/README.md) plugin.

## Deep dives

- [Connecting a client](connecting.md): the three ways a client reaches the server, and why two of
  them are not implemented here.
- [Bridges and virtual players](bridges.md): registering another protocol's player as a client, and
  virtual players.

## Module layout

| Module | Role |
|---|---|
| `provider.py` | Server lifecycle, client events, the virtual player API |
| `player.py` | The player: playback, grouping, metadata |
| `playback.py` | The playback pipeline, per-channel processing and timed frame commits |
| `bridge_manager.py` | Shared lifecycle for bridges from other protocols |
| `bridge_role.py` | The role that receives audio and forwards it to a bridged player |
| `synchronizer_role.py` | Computes visualization features for external consumers |
| `security.py` | Persisting the server's own identity keypair |
| `helpers.py`, `constants.py` | Bridge client id derivation, prefixes and config keys |

It depends on the protocol library, including its server, plus a media library used by the playback
pipeline and an imaging library for artwork.

## What a client gets

Volume and mute, sample-accurate synchronized playback with other clients, per-device processing
such as an equaliser, grouping into multi-room sets, metadata including artwork and progress, and
full transport and queue control from the client side.

The last point is worth noting: Sendspin clients **control** playback as well as rendering it, which
is why a web player can act as a full remote rather than only a speaker.

## Its own server, its own port

The protocol server runs on its own port, separate from the API. That is deliberate and matches the
reasoning for the audio stream server: a client is an embedded device or a browser, and pushing the
protocol through the authenticated API would impose a handshake and a credential on things that
often have neither.

Authentication for the clients that *do* need it is handled one layer up, by the webserver, which is
why this provider registers no signalling commands and pulls in no connection-brokering dependency
of its own. See [Connecting a client](connecting.md).

## Related architecture docs

- [Playback](../../../docs/architecture/playback.md) for where this protocol sits in the pipeline.
- [Protocol linking](../../../docs/architecture/protocol-linking.md) for bridges as derived
  transports.
- [Grouping and volume](../../../docs/architecture/grouping-and-volume.md) for the grouping it
  backs.
- [API and auth](../../../docs/architecture/api-and-auth.md) for the authenticated proxy and remote
  access.

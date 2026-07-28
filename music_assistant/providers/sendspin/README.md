# Sendspin Player Provider

The Sendspin provider implements the [Sendspin Audio Protocol](https://github.com/Sendspin/spec), developed by the Open Home Foundation. It is the native playback protocol built into Music Assistant, providing synchronized audio playback across multiple clients.

## Overview

Sendspin enables:
- **Synchronized multi-room audio** with sample-accurate playback across devices
- **Per-player DSP processing** for individual equalizer and volume settings
- **Real-time metadata** including artwork, track info, and playback state
- **Bidirectional control** allowing clients to control playback

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Music Assistant Server                          │
│                                                                       │
│  ┌─────────────────┐     ┌─────────────────┐     ┌───────────────┐  │
│  │ SendspinProvider│────▶│  SendspinServer │────▶│ Audio Streams │  │
│  │                 │     │   (port 8927)   │     │               │  │
│  └─────────────────┘     └────────┬────────┘     └───────────────┘  │
│                                   │                                  │
└───────────────────────────────────┼──────────────────────────────────┘
                                    │
                 ┌──────────────────┼──────────────────┐
                 │                  │                  │
                 ▼                  ▼                  ▼
          ┌───────────┐      ┌───────────┐      ┌───────────┐
          │  Browser  │      │ Mobile App│      │  Hardware │
          │ (WebRTC)  │      │ (WebRTC)  │      │(WebSocket)│
          └───────────┘      └───────────┘      └───────────┘
```

## Connection Methods

### 1. Direct WebSocket Connection (Local Network)

Hardware devices and local clients can connect directly to the Sendspin server:

```
ws://<ma-server-ip>:8927/sendspin
```

This is suitable for:
- Hardware players on the local network
- Native apps with direct network access
- Development and testing

### 2. WebRTC Connection (Remote/NAT Traversal)

For web browsers and mobile apps that need to work across networks (including when accessing Music Assistant remotely), we use WebRTC DataChannels. The signaling happens through the authenticated MA API WebSocket connection.

#### WebRTC Connection Flow

```
┌──────────────┐                    ┌─────────────────┐
│   Client     │                    │   MA Server     │
│  (Browser)   │                    │                 │
└──────┬───────┘                    └────────┬────────┘
       │                                     │
       │  1. sendspin/ice_servers            │
       │────────────────────────────────────▶│
       │                                     │
       │  ICE servers (STUN/TURN)            │
       │◀────────────────────────────────────│
       │                                     │
       │  2. Create RTCPeerConnection        │
       │     Create DataChannel              │
       │                                     │
       │  3. sendspin/connect {offer}        │
       │────────────────────────────────────▶│
       │                                     │ Create RTCPeerConnection
       │                                     │ Connect to local Sendspin
       │  {session_id, answer, ice}          │
       │◀────────────────────────────────────│
       │                                     │
       │  4. sendspin/ice {candidate}        │
       │────────────────────────────────────▶│
       │                                     │
       │  5. DataChannel opens               │
       │◀═══════════════════════════════════▶│
       │     Sendspin protocol messages      │
       │                                     │
```

#### API Commands for WebRTC

The Sendspin provider registers these API commands for WebRTC signaling:

| Command | Parameters | Description |
|---------|------------|-------------|
| `sendspin/ice_servers` | None | Get ICE server configurations (STUN/TURN). Returns HA Cloud TURN servers if available. |
| `sendspin/connect` | `offer: {sdp, type}` | Initiate WebRTC connection with SDP offer. Returns `{session_id, answer, ice_candidates}`. |
| `sendspin/ice` | `session_id, candidate` | Exchange ICE candidates for NAT traversal. |
| `sendspin/disconnect` | `session_id` | Clean up WebRTC session. |

### ICE Server Configuration

The provider automatically provides optimal ICE servers:

1. **Home Assistant Cloud TURN servers** (if HA Cloud is available with active subscription)
   - Provides reliable connections through firewalls and symmetric NAT
   - Requires HA 2025.12.0b6 or later

2. **Public STUN servers** (fallback)
   - `stun:stun.l.google.com:19302`
   - `stun:stun.cloudflare.com:3478`
   - `stun:stun.home-assistant.io:3478`

## Implementing a Sendspin Client

### Web Browser (TypeScript/JavaScript)

For web browsers, use the WebRTC approach with the MA API for signaling:

```typescript
// 1. Get ICE servers from the server
const iceServers = await api.sendCommand("sendspin/ice_servers");

// 2. Create RTCPeerConnection
const peerConnection = new RTCPeerConnection({ iceServers });

// 3. Create DataChannel
const dataChannel = peerConnection.createDataChannel("sendspin", {
  ordered: true,
});

// 4. Create and send offer
const offer = await peerConnection.createOffer();
await peerConnection.setLocalDescription(offer);

const response = await api.sendCommand("sendspin/connect", {
  offer: { sdp: offer.sdp, type: offer.type },
});

// 5. Set remote description (answer)
await peerConnection.setRemoteDescription(
  new RTCSessionDescription(response.answer)
);

// 6. Add ICE candidates from server
for (const candidate of response.ice_candidates) {
  await peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
}

// 7. Handle local ICE candidates
peerConnection.onicecandidate = (event) => {
  if (event.candidate) {
    api.sendCommand("sendspin/ice", {
      session_id: response.session_id,
      candidate: {
        candidate: event.candidate.candidate,
        sdpMid: event.candidate.sdpMid,
        sdpMLineIndex: event.candidate.sdpMLineIndex,
      },
    });
  }
};

// 8. Use dataChannel for Sendspin protocol
dataChannel.onopen = () => {
  // DataChannel ready - use sendspin-js library
};
```

### Mobile Apps

Mobile apps can use the same WebRTC approach for reliable connectivity across networks. The connection is established through the authenticated MA API, so no additional authentication is needed for the Sendspin connection itself.

### Hardware Devices

Hardware devices on the local network can connect directly via WebSocket:

```python
import websockets

async with websockets.connect("ws://192.168.1.100:8927/sendspin") as ws:
    # Sendspin protocol communication
    pass
```

## Player Features

Sendspin players support:

- **Volume control** - Set volume level (0-100) and mute
- **Synchronized playback** - Sample-accurate sync across grouped players
- **Per-player DSP** - Individual equalizer settings per device
- **Player grouping** - Create multi-room audio groups
- **Metadata display** - Track info, artwork, progress
- **Playback control** - Play, pause, stop, next, previous
- **Repeat/Shuffle** - Queue control from clients

## Files

| File | Description |
|------|-------------|
| `provider.py` | Main provider class, handles WebRTC signaling and server lifecycle |
| `player.py` | Player implementation with playback, grouping, and metadata handling |
| `playback.py` | Playback pipeline with DSP channel processing and timed frame commits |
| `bridge_manager.py` | Shared lifecycle management for Sendspin bridges (see below) |
| `bridge_role.py` | `BridgePlayerRole`: receives audio from the PushStream and forwards it to an external player |
| `synchronizer_role.py` | `SynchronizerRole`: computes visualization features for external consumers (e.g. Hue Entertainment) |
| `security.py` | Server identity (Noise keypair) persistence |
| `helpers.py` | Shared helpers, including bridge client ID derivation |
| `constants.py` | Prefixes and config keys |
| `__init__.py` | Provider setup entry point |
| `manifest.json` | Provider metadata |
| `strings.json` | Translatable labels for the provider's config entries |
| `icon.svg` | Provider icon (also `icon_dark.svg` and `icon_monochrome.svg`) |

## Dependencies

- `aiosendspin` - Async Sendspin protocol implementation
- `aiolibdatachannel` - WebRTC implementation for Python (used for WebRTC bridging)
- `PIL/Pillow` - Image processing for artwork

## External Players (Protocol Bridges)

The Sendspin server supports external player registration for bridging other audio protocols. This enables cross-protocol grouping where Sendspin handles timing and synchronization.

### How External Players Work

External players are registered programmatically via `server_api.register_external_player()`:

1. The bridge provider creates a `ClientHelloPayload` with the device info and supported capabilities
2. The Sendspin server creates a `SendspinClient` and triggers `ClientAddedEvent`
3. The Sendspin provider creates a `SendspinPlayer` for this client
4. Protocol linking attaches the SendspinPlayer to the bridged player

Step 4 is deterministic rather than identifier-based: a bridge calls `register_bridge_underlying_player()` before registering the external player, so the resulting SendspinPlayer carries a **derived-transport edge** (`underlying_player_id`) pointing at the player it rides on. Protocol linking then parents it alongside that player without any identifier matching, and records the edge as `derived_from` on the resulting `OutputProtocol`. Bridges additionally register device identifiers (MAC, CAST_UUID, AIRPLAY_ID, …) via `register_bridge_identifiers()` for cross-protocol matching, and the bridge's `client_id` is derived from the device's MAC or UUID (`bridge_client_id_from_mac` / `bridge_client_id_from_uuid`).

`SendspinBridgeManagerBase` in `bridge_manager.py` owns the shared lifecycle: a bridge only exists while the player it rides on exists and is enabled.

### Implemented Bridges

| Provider | Bridge Location | Client ID derived from | Audio path |
|----------|-----------------|------------------------|------------|
| AirPlay | `airplay/sendspin_bridge.py` | MAC address | Audio flows through the bridge into the AirPlay CLI |
| Local Audio | `local_audio/sendspin_bridge.py` | Device UUID | Audio flows through the bridge to the local soundcard |
| Chromecast | `chromecast/sendspin_bridge.py` | MAC address (UUID for cast groups) | No audio through the bridge: the Cast receiver app runs a JS Sendspin client that connects to the server directly |
| MSX | `msx_bridge/sendspin_bridge.py` | MSX player id | No audio through the bridge: the TV kiosk runs a vendored Sendspin JS client |

### Implementing a New Bridge

To bridge another protocol to Sendspin:

1. Create a `ClientHelloPayload` with the device's capabilities
2. Declare the derived-transport edge with `register_bridge_underlying_player()` (and any identifiers with `register_bridge_identifiers()`) before registering
3. Call `register_external_player()` with an `on_stream_start` callback
4. Create a custom `Role` subclass to receive audio via `on_audio_chunk()`, or reuse `BridgePlayerRole`

See the [AirPlay Sendspin Bridge](../airplay/sendspin_bridge.py) for a complete implementation example that streams audio, and the [Chromecast bridge](../chromecast/sendspin_bridge.py) for one where the device runs its own Sendspin client instead.

## Virtual Players

Other providers (typically plugins) can host a shared listening session on a
hidden, server-side "anchor" player via the public virtual player API:

```python
sendspin = mass.get_provider("sendspin")
player_id = await sendspin.create_virtual_player(
    owner_instance_id=self.instance_id,
    display_name="My Session",
)
...
await sendspin.remove_virtual_player(player_id)
```

A virtual player owns its own PlayerQueue and leads a native Sendspin group,
but never renders audio itself. Guest players (e.g. web players) are attached
and detached through standard grouping (`mass.players.cmd_set_members`) and
receive the audio stream, with join-catchup for late joiners. Because the
anchor is server-side and permanent for the session's lifetime, guests coming
and going never cause a group leader transfer.

Virtual players are hidden from the UI and not exposed to Home Assistant by
default, expose no volume controls (member volumes apply instead), and are
removed automatically when the owning provider unloads. Stale configurations
of virtual players whose owner no longer exists are swept on provider startup.

Virtual players are never auto-restored: when the Sendspin provider reloads
(or the server restarts), the owning provider must call `create_virtual_player`
again to restore its session anchor. The player's configuration (including the
owner marker) may persist across restarts and is reused when the same owner
recreates the same player id; it is deleted on `remove_virtual_player` or swept
at startup once the owner provider no longer exists.

## Related Documentation

- [Sendspin Protocol Specification](https://github.com/Sendspin/spec)
- [Music Assistant Remote Access](../../controllers/webserver/README.md)

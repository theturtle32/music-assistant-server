# Writing a player provider

Part of the [player controller](README.md). See `_demo_player_provider` for an annotated template.

## Report state, do not resolve it

Set the internal attributes from what the device tells you, then ask for a state update. Do not try
to compute what the user should see: the framework layers user customizations and the power, volume
and mute control chains on top, and a provider that second-guesses that will fight it.

## Pick the right player type

Use the plain player type for devices with native vendor support, meaning the vendor's own
hardware. Use the protocol type for generic endpoints from third-party manufacturers discovered
over a shared protocol.

The distinction is about who made the device, not what it speaks, and it decides whether your
player is the one the user sees or gets wrapped behind one.

## Identifiers are what make linking work

Populate the device identifiers. This is the single thing that determines whether your device is
correctly recognised as the same box another provider already found.

**Validate MAC addresses before adding them.** The validation helper rejects all-zero and broadcast
addresses, which would otherwise cause false matches between unrelated devices. The controller
attempts an address lookup to resolve real MACs where it can.

Add every identifier you have, in reliability order: MAC address, serial number, UUID,
protocol-specific stable ids, then IP address. IP is used only as a last resort, so supplying it is
useful but never sufficient.

Filter out devices that another provider should own. A passive satellite of a native system, for
example, should not also appear as an independent endpoint.

Everything after that is automatic: the controller finds matching protocol players, links them, and
replaces any existing wrapper for the device.

## Delegate rather than reimplement

If your player has no playback capability of its own and routes commands to a linked protocol
player, subclass the protocol-backed base and supply only the protocol players backing it. It
already handles availability, setup passthrough, delegated state and transport, and surfacing an
external source playing on a linked protocol.

## Things to get right

Report availability honestly. A device that is reachable but not yet usable, such as one awaiting
pairing, should say so rather than appearing broken, and the reason should be surfaced so the UI can
act on it.

Expect to be commanded while unpowered. Several command paths power a player on first, so handle
that rather than assuming a command arrives only when ready.

Do not assume your player is the audio path. Once linked, the audio may go out over a protocol
player instead, and group commands may be translated onto it.

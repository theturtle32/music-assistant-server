# Setup flows

Part of the [config controller](README.md). The authoring guide for provider setup flows lives at
[developers.music-assistant.io](https://developers.music-assistant.io/setup-flows/); this covers
how the engine behaves.

Anything interactive, meaning credentials, OAuth logins and pairing, runs through the flow engine
in `flows.py`.

## Authoring shape

A flow is one plain coroutine in the provider's `setup_flow.py`. The session handle it receives
publishes a step and suspends until the user responds, so the author writes a linear sequence
rather than a state machine.

| Step | Does |
|---|---|
| Form | Renders config entries and returns the validated values |
| External | Sends the user to an OAuth-style URL and waits for the callback on the flow's own route |
| Progress | Display-only status, optionally with an image such as a pairing QR code |
| Finish | Persists the collected values as setup data and creates or reloads the target |
| Abort | The terminal step for a cancelled, expired or failed flow |

Authors signal outcomes with exceptions rather than return codes. Aborting ends the flow cleanly,
an expiry is raised into the coroutine when a step's deadline passes, and a failure to apply the
values is raised out of the finish step, which an author may catch to re-render a form with an
error.

## Engine behaviour

**One flow per target.** Starting a new flow aborts any lingering one for the same provider or
player, so a user who navigated away does not leave a session holding the target.

**Cancellation is cooperative.** Aborting cancels the flow task first, so an author's cleanup, such
as tearing down a pairing session, runs before the terminal step is published. That cleanup is
bounded by a timeout.

**Idle flows are swept.** A flow with no interaction for fifteen minutes is aborted as timed out,
unless its current step advertises a longer countdown of its own.

**Zero-input providers are uniform.** A provider that ships no `setup_flow.py` needs no input at
all, so creating it returns a synthesized finish step. Clients therefore have one code path for
every provider, and the manifest records which kind a provider is.

**Wrapper players delegate.** A player whose own setup is a no-op but which wraps protocol children
that need pairing delegates to the child's flow, directly when one child needs setup or through a
selection form when several do. The session is re-pointed at the chosen child, so its steps
localize under that child's provider and the finish step persists to its config.

**Failures roll back.** Every finish handler snapshots the existing setup data, writes the merged
values, and restores the snapshot when creating or reloading the target fails. A failed provider
creation removes the half-written config entirely.

## Reaching clients

Flow steps reach clients as events. Because a step can carry prefilled values and OAuth URLs, the
WebSocket layer filters those events by scope instead of broadcasting them. The scopes of recently
finished flows are retained briefly, so a terminal step published just after the flow left the
registry can still be resolved.

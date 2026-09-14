# Shared playback sessions

A helper shared by the plugins that host a group listening experience, currently
[party](../providers/party/README.md) and [music_quiz](../providers/music_quiz/README.md).

Both needed the same thing: a queue that a group of guests listens to together, with guests
optionally joining on their own devices. Rather than each plugin inventing it, a session object
wraps one player that owns a queue.

## Two modes

| Mode | The queue lives on | Guests |
|---|---|---|
| Venue | An existing real player, playing out loud | May optionally listen in on their own device, when the venue player can group with it |
| Remote | A hidden virtual player on the native synchronized protocol | Every guest's web player attaches, so all playback happens on guests' devices, silent-disco style |

The owning plugin drives playback on the session's queue and closes it when the session ends.

**A queue id is a player id**, so the same code path works for a real speaker and a virtual one.
That is the whole reason this abstraction is thin enough to be worth having.

## Listening in is grouping, not a second stream

A guest joining is a group membership change, not another audio stream.

Eligibility asks whether the host player supports setting members and whether the guest player
appears among the players the host can group with. Attaching then issues an ordinary set-members
command. Delegating the compatibility question that way means all the protocol expansion and
translation described in [grouping and volume](../../docs/architecture/grouping-and-volume.md) is
already handled, for a real venue player and a virtual host alike.

## Guests are tracked, not merely added

The session keeps its own set of guest listeners, separate from the host's current group.

A guest whose device is offline or momentarily incompatible stays tracked rather than being
dropped, and a restore pass re-attaches any tracked guest missing from the host's group. Without
that, a playback transition would quietly lose a guest whose phone slept.

Teardown is mode-dependent. A remote session removes the virtual player, and its queue with it. A
venue session detaches only the guests it added and leaves the venue player untouched, because that
player belonged to the household before the session existed.

## The sharp edge

A remote session's virtual player lives in the **memory of the provider that hosts it**, so it
disappears when that provider reloads. The session does not survive on its own, and the owning
plugin is responsible for re-creating it; passing the same session id yields the same player id, so
a re-creation is transparent to clients.

Creation also carries real cancellation-safety machinery, because a cancelled creation that
nevertheless completes would leak an orphaned virtual player into a provider nobody is tracking it
in.

## Related

- [plugins](../../docs/architecture/plugins.md) for the plugin categories this belongs to.
- [api and auth](../../docs/architecture/api-and-auth.md) for guest accounts and join codes, which
  are a separate mechanism from this one.

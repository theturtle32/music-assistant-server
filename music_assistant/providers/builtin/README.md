# Music Assistant (builtin)

The music provider for media that belongs to **this server** rather than to any service: URLs a
user added by hand, and playlists stored here instead of on a provider.

It is builtin and always present, which is what lets the rest of the codebase assume there is
somewhere to put a manually added stream or a playlist of the household's own.

## What it holds

| Kind | Stored as |
|---|---|
| Manually added tracks and radio stations | Library rows with a URL, plus whatever the user edited on them |
| Server-owned playlists | An M3U file per playlist in the storage directory |

It declares browse, the library listings and their edit counterparts, and playlist creation, so its
items behave like any other provider's throughout the library.

Server-owned playlists are also the only playlists that carry an access record of their own; a
provider's playlist follows the sharing of its source. See
[Media sub-controllers](../../controllers/music/media/README.md) and
[The API and authentication](../../../docs/architecture/api-and-auth.md).

## Manual items are stored as the caller gave them

Adding anything else to the library re-fetches it from its provider rather than trusting the
object passed in. A manual URL track or radio station is the documented exception, because the
name and artwork a user typed exist nowhere else to re-fetch from. See
[Matching and merging](../../controllers/music/media/matching.md).

That exception is why the two guards below matter: this is the one input path where user-supplied
fields reach storage directly.

## Two guards worth keeping

**A playlist id doubles as its file name.** Anything carrying a path separator, a relative segment,
an absolute path or a null byte is refused rather than turned into a path, since otherwise a
crafted id would read or write outside the playlists directory.

**A manual item's image must be a remote URL or an inline data URI**, never a local file path.
Embedded artwork legitimately carries the track's own stream URL as its path, which is why the
remote form is allowed at all; permitting a local path would turn artwork into a way to point the
image endpoint at an arbitrary file on the server.

Both read as removable tidying if you do not know what they are for. They are not.

## Related architecture docs

- [The media library](../../../docs/architecture/media-library.md) for how these items join the
  library alongside provider items.
- [Providers](../../../docs/architecture/providers.md) for the provider model and features.
- [The API and authentication](../../../docs/architecture/api-and-auth.md) for ownership and
  sharing.

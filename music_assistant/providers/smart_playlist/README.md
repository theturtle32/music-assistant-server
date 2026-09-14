# Smart Playlist

Builds rule-based playlists from genre, artist, album, favorites, similar tracks, release year,
album type, explicit content and more. It declares browse and recommendations, plus the ungated
playlist fetch pair.

The playlists it writes are ordinary library playlist rows carrying the dynamic flag. Nothing
downstream needs to know they were generated; see
[controllers/music](../../controllers/music/README.md). The flag decides whether tracks are
re-evaluated fresh on every play or frozen once.

## AI is pure garnish here

With the description option on, the provider asks a model for a one-or-two-sentence description of
the playlist, passing the rules through their human-readable form and requesting the response in
the configured metadata language.

This is the clearest example in the tree of AI as an optional extra. Every failure path, meaning
the feature disabled, no provider loaded, an exception, or an empty reply, returns nothing. **The
playlist works identically without it; only the description field is empty.**

Descriptions are persisted alongside the rules, so a working description survives an AI backend
going away.

## Related architecture docs

- [Plugins](../../../docs/architecture/plugins.md) for the plugin provider model and its hooks.
- [Media library](../../../docs/architecture/media-library.md) for dynamic playlists as library rows.
- [AI and MCP](../../../docs/architecture/ai-and-mcp.md) for the AI provider-feature contract.

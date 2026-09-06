---
name: arch_docs_stack1_models
overview: "Refresh docs/architecture/03-player-model.md and docs/architecture/11-plugin-system.md to cover upstream additions to the Player and PluginProvider models since the docs were originally written: five new player notification hooks (on_protocol_player_updated, on_protocol_parent_updated, on_group_member_updated, on_group_updated, on_sync_parent_updated), the auto-set of PlayerFeature.SELECT_SOURCE for multi-entry source lists, the new PluginProvider methods get_tts_message and ai_query, and the use of PluginSource.elapsed_time for player progress."
todos:
  - id: branch
    content: Cut docs/architecture-models-update from docs/architecture
    status: pending
  - id: edit_player_model
    content: Update docs/architecture/03-player-model.md — add the five player notification hooks and the SELECT_SOURCE auto-set behavior
    status: pending
  - id: edit_plugin
    content: Update docs/architecture/11-plugin-system.md — add get_tts_message, ai_query, and PluginSource.elapsed_time
    status: pending
  - id: verify
    content: pre-commit + visual diff vs docs/architecture
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture
    status: pending
isProject: false
---

# Stack 1 — Player & Plugin model deltas

## Branch

Cut `docs/architecture-models-update` from `docs/architecture` (PR #6 head).

```bash
git fetch origin
git checkout docs/architecture
git pull --ff-only origin docs/architecture
git checkout -b docs/architecture-models-update
```

## Edits — `docs/architecture/03-player-model.md`

### Add a new section: "Update Notification Hooks"

Insert immediately before the existing "Player Control Commands" table (around line 200, after the Feature Sets section). Heading depth: `##`.

The five hooks live on `Player` in [music_assistant/models/player.py](music_assistant/models/player.py) at lines 667–706:

```python
def on_protocol_player_updated(self, protocol_player, changed_values): ...
def on_protocol_parent_updated(self, protocol_parent, changed_values): ...
def on_group_member_updated(self, member_player, changed_values): ...
def on_group_updated(self, group_player, changed_values): ...
def on_sync_parent_updated(self, sync_parent, changed_values): ...
```

Each is an optional override; the default implementation simply calls `mass.players.trigger_player_update(self.player_id)`. Subclasses override when they need to react to a *related* player's state change.

Suggested wording:

> ### Update Notification Hooks
>
> Beyond reacting to its own state changes, a `Player` can override one of five callbacks to be notified when a *related* player's state changes. The controller dispatches these from `_forward_state_update` whenever a relevant relationship is in scope. Default implementations call `trigger_player_update` to refresh the receiving player's own state.
>
> | Hook | Fires when |
> |---|---|
> | `on_protocol_player_updated(protocol_player, changed_values)` | One of this player's linked protocol players (e.g. RAOP for an AirPlay device) updated |
> | `on_protocol_parent_updated(protocol_parent, changed_values)` | The protocol parent of this protocol player updated |
> | `on_group_member_updated(member_player, changed_values)` | A group member of this group player updated |
> | `on_group_updated(group_player, changed_values)` | A group player this player belongs to updated |
> | `on_sync_parent_updated(sync_parent, changed_values)` | The sync parent (ad-hoc sync leader) of this player updated |
>
> All five take the source `Player` and a `changed_values` dict mapping attribute name to a `(previous, new)` tuple. See [04-player-controller.md](04-player-controller.md#state-update-fan-out) for the dispatch flow.

(The cross-link to `04-player-controller.md#state-update-fan-out` will be live once Stack 2 lands; until then it dangles, which is acceptable.)

### Update the `supported_features` description

Find the paragraph or row mentioning `PlayerFeature.SELECT_SOURCE`. Add: "The controller auto-sets `PlayerFeature.SELECT_SOURCE` when a player's *final* source list (after merging plugin sources, queue, etc.) has more than one entry — set explicitly in [music_assistant/controllers/players/controller.py](music_assistant/controllers/players/controller.py) (#3789)."

## Edits — `docs/architecture/11-plugin-system.md`

### Update the "PluginProvider Base Class" section

Find the table or list describing `PluginProvider` methods. Add these two rows:

| Method | When called | Purpose |
|---|---|---|
| `get_tts_message(message, language=None) -> StreamDetails` | When the plugin declares `ProviderFeature.TTS` | Convert text to speech and return `StreamDetails` for streaming the resulting audio |
| `ai_query(query) -> str` | When the plugin declares `ProviderFeature.AI_QUERY` | Send a natural-language query to an AI backend and return the response text |

Both raise `NotImplementedError` by default. Source: [music_assistant/models/plugin.py](music_assistant/models/plugin.py) lines 178 and 190. Both were added by #3607 ("Add AI_QUERY and TTS to HA Plugin").

### Update PluginSource description

Find the paragraph or row describing `PluginSource.elapsed_time`. Add: "The player controller now uses `PluginSource.elapsed_time` (when set) for player progress reporting — see #3652. This means a plugin can drive accurate position even when MA is not the timing source (e.g. Spotify Connect reporting playhead from the Spotify cloud)."

## Verification

```bash
pre-commit run --files docs/architecture/03-player-model.md docs/architecture/11-plugin-system.md
git diff --stat docs/architecture
```

## Commit + PR

Single commit message:

```
docs(architecture): document new Player notification hooks and PluginProvider AI/TTS methods

- Player gains five optional override hooks (on_protocol_player_updated,
  on_protocol_parent_updated, on_group_member_updated, on_group_updated,
  on_sync_parent_updated) that fire when related players' state changes
  (#3789 et al.).
- PluginProvider gains get_tts_message and ai_query (#3607).
- PluginSource.elapsed_time is now used for player progress (#3652).
- PlayerFeature.SELECT_SOURCE is auto-set when the final source list
  is multi-entry (#3789).
```

PR base: `docs/architecture` on `theturtle32/music-assistant-server`.

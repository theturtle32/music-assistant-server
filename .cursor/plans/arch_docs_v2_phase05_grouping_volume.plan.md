---
name: arch_docs_v2_phase05_grouping_volume
overview: "Phase 5. The biggest single correction in the refresh: sync groups moved from a power-driven lifecycle to a session-driven one (#3947), inverting the documented stop/dissolve behavior and removing POWER from default features. Also fix dynamic leader switch, allowed-members config naming, and rewrite the plugin volume path around AudioSource (#3938)."
todos:
  - id: preflight
    content: "Pre-flight: verify SyncGroupPlayer session lifecycle, supported_features, dissolve triggers, leader switch, and the AudioSource volume path against the working tree"
    status: completed
  - id: group_table
    content: "06-grouping.md: fix the three-grouping-models comparison table, especially the inverted 'dissolves on stop' row"
    status: completed
  - id: group_session
    content: "06-grouping.md: rewrite the sync group lifecycle around is_active_session, idle grace, and reform debounce; POWER is opt-in via fake power"
    status: completed
  - id: group_formation
    content: "06-grouping.md: rewrite the formation and dissolution flows and diagrams for the session model"
    status: completed
  - id: group_dynamic
    content: "06-grouping.md: fix dynamic leader switch (no supports_dynamic_leader_switching), add reform debounce and ad-hoc leadership transfer"
    status: completed
  - id: group_config
    content: "06-grouping.md: rename CONF_MEMBERS_FILTER to CONF_ALLOWED_MEMBERS; fix can_group_with aggregation for dynamic groups"
    status: completed
  - id: group_playmedia
    content: "06-grouping.md: add the play_media group-override interaction and cross-link 04-player-controller.md"
    status: completed
  - id: volume_plugin
    content: "07-volume.md: rewrite the plugin volume callback path for AudioSource (on_volume_change, queue ownership)"
    status: completed
  - id: volume_misc
    content: "07-volume.md: add follow_protocol, device_volume redirect, fake mute reporting fix, and the group_volume exclude_self nuance"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 5 — Grouping and volume

Files: `docs/architecture/06-grouping.md`, `docs/architecture/07-volume.md`.

`06-grouping.md` was the most heavily revised doc in round 1, and upstream #3947 then inverted its
central premise. Expect a structural rewrite of the sync-group half, not line edits.

Related in-tree READMEs: `music_assistant/providers/sync_group/README.md` (itself stale — Phase 1
fixes it; make sure the two end up consistent) and `providers/universal_player/README.md`.

## The core change: #3947, "Stabilize group players"

Sync group membership is now a **session**, not a power state.

- `stop()` **dissolves** the sync group immediately, unless the user has pinned it with fake power
  (`_attr_powered is True`). The doc's comparison table says "Dissolves on stop: No — stop() only
  stops leader", which is now backwards for the default case.
- A natural queue transition to IDLE starts a **10-second idle grace** (`IDLE_GRACE_SECONDS`) and
  then dissolves.
- `PlayerFeature.POWER` is **intentionally omitted** from `SyncGroupPlayer.supported_features` by
  default; it is added only when the user configures `PLAYER_CONTROL_FAKE`. The doc currently
  promotes POWER to base features and calls `_attr_powered` the source of truth.
- Session capture is `is_active_session` — sync leader set, idle grace pending, or reform debounce
  pending. Dormant sync groups no longer capture their members, which is what
  `__final_active_group` now tests (cross-link Phase 4).
- Formation is triggered by `play_media` / `play`, and optionally by `power()` for fake-power users.
  The formation diagram currently starts at `power(True)`; rewrite it.
- `play_media` no longer implicitly triggers fake power for default sync groups; the controller
  calls `_form_syncgroup` from the provider.

Keep the round-1 note explaining why `_handle_set_members` is called directly rather than
`cmd_set_members` (bypassing the active-group redirect to avoid loops) — that is still correct and
was hard-won.

## Other grouping corrections

- **`CONF_MEMBERS_FILTER` → `CONF_ALLOWED_MEMBERS`** (`allowed_members`).
- **`can_group_with` for dynamic groups** aggregates compatibility across all current members, not
  just the leader, which is what allows protocol switches mid-session.
- **Dynamic leader switch:** the doc references `PlayerProvider.supports_dynamic_leader_switching`,
  which **does not exist**. The capability is expressed only by the
  `PROVIDERS_WITH_DYNAMIC_LEADER_SWITCH` tuple (`airplay`, `snapcast`, `sendspin`). Add
  `REFORM_DEBOUNCE_SECONDS` (2s) and the `_dissolve_and_reform` pipeline for cascaded leader
  removals (#4412, #4815).
- **Ad-hoc sync:** when a sync leader removes itself while playing,
  `_transfer_ad_hoc_leadership` may promote a remaining member instead of dissolving outright.
- `_handle_set_members` can add to a dynamic sync group when all members are offline (#4814).
- **New interaction section:** `CONF_PLAY_MEDIA_OVERRIDES_GROUP` and
  `_release_player_for_play_media` (Phase 4) mean playing to a captured player can now break it out
  of its group. Document the grouping-side view and cross-link.
- Note on scope: PR #3847 (AirPlay2 sync selection) predates the doc baseline and is already
  reflected. Post-baseline AirPlay group work is #4424, #4985, #5052, #4821 — check whether any of
  it changes documented behavior before adding it.

## `07-volume.md`

- **Plugin volume path (rewrite).** The section is built on `PluginSource`,
  `_get_active_plugin_source`, `plugin_source.in_volume`, and `in_use_by`. Current code uses
  `_get_active_audio_source`, `PluginProvider.on_volume_change(source_id, volume)`, gated on queue
  ownership (`active_queue.queue_id == player.player_id`) (#3938). Update the mermaid diagram, the
  "Plugin Volume Callbacks" section, and the "Volume Command Flow Summary".

  Careful: round 1 fixed the *ordering* here so that plugin `on_volume` fires **before** the
  `volume_control type?` decision. Preserve that ordering finding while renaming the mechanism.
- **`follow_protocol`:** document `PLAYER_CONTROL_PROTOCOL` as the default auto-select value for
  volume and mute control.
- **Protocol redirect:** upstream passes `device_volume` after scaling on the visible player
  (#4461); the doc implies logical volume throughout, which loses min/max scaling.
- **Fake mute:** `__final_volume_muted_state` reads `ATTR_FAKE_MUTE` explicitly. Fake mute never
  reported a muted state at the doc's baseline; #4839 fixed it. The doc describes the broken
  behavior.
- **`group_volume`:** same `exclude_self` nuance as Phase 4 — `PlayerType.PLAYER` sync leaders
  include themselves in the max calculation.
- The group volume interpolation algorithm and snapshot behavior were verified as still matching
  `set_group_volume()`. Leave them alone.

## Verification

- `rg "is_active_session|IDLE_GRACE_SECONDS|REFORM_DEBOUNCE_SECONDS|PROVIDERS_WITH_DYNAMIC_LEADER_SWITCH|_dissolve_and_reform|_transfer_ad_hoc_leadership"`.
- `rg "CONF_ALLOWED_MEMBERS|CONF_MEMBERS_FILTER"` — confirm the rename.
- `rg "supports_dynamic_leader_switching"` — should return nothing.
- `rg "on_volume_change|_get_active_audio_source|ATTR_FAKE_MUTE"`.
- Confirm the mermaid diagrams still render (no stray whitespace in node definitions — a round-1
  review caught exactly that).
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): session-based sync group lifecycle and AudioSource volume routing

Phase 5 of the upstream/dev refresh.
```

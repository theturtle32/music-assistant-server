---
name: arch_docs_v2_phase06_protocol_linking
overview: "Phase 6. Refresh 05-protocol-linking.md: Sendspin bridges are now first-class derived transports with derived_from, universal players are retained when their protocol links cannot migrate, active output protocols are released at session end, disabled linked protocols are recoverable, and player pairing/setup flows gate availability."
todos:
  - id: preflight
    content: "Pre-flight: verify protocol restore/merge behavior, derived transports, and output protocol release against the working tree"
    status: completed
  - id: restore
    content: "05-protocol-linking.md: update the cached-parent restore flow with identifier merge and universal merge checks"
    status: completed
  - id: migration
    content: "05-protocol-linking.md: correct Flow 3 — universal players are kept when links cannot migrate; settings and group memberships are preserved"
    status: completed
  - id: derived
    content: "05-protocol-linking.md: add a derived transports section for Sendspin bridges and derived_from"
    status: completed
  - id: selection
    content: "05-protocol-linking.md: add active output protocol release at session end and disabled-protocol recovery"
    status: completed
  - id: setup
    content: "05-protocol-linking.md: document pairing / needs_setup gating and its effect on availability"
    status: completed
  - id: providers
    content: "05-protocol-linking.md: refresh the participating-provider notes (AirPlay rearchitecture, local_audio, new native providers) and fix the line-count reference"
    status: completed
  - id: verify
    content: pre-commit, confirm the diff touches only docs, commit and push
    status: completed
isProject: false
---

# Phase 6 — Protocol linking

File: `docs/architecture/05-protocol-linking.md`. Medium-sized: the documented flows are broadly
right, but several outcomes and a whole mechanism (derived transports) are missing.

`protocol_linking.py` line count is stale (~1870 → ~2439). Re-measure.

Related in-tree README: `music_assistant/providers/universal_player/README.md`. Phase 1 may have
corrected it; keep the two consistent.

## Restore flow (Flow 1)

`_try_restore_cached_parent()` does more than the doc says. It now also merges identifiers into the
universal parent, calls `_update_universal_device_info` and `_check_merge_universal_players`, and
handles link refusal when a duplicate domain is already linked. The doc's description of leaving a
protocol unparented and scheduling re-evaluation when the cached parent isn't registered is still
correct — keep it and add the merge-on-restore behavior.

## Native replaces universal (Flow 3)

The doc states the universal player always disappears. #4413 changed this: the universal player is
**kept** when its protocol links cannot migrate to the native player. Also document that settings
and group memberships are preserved across merge/replace (#4921, #4929, #4931).

## Derived transports (new section)

`local_audio` and `airplay` register **derived Sendspin bridges** as first-class linked protocols,
carrying `derived_from` on the output protocol entry (#4596, #4609). This is a genuinely new
mechanism and the doc has no equivalent concept. Cover:

- What a derived transport is and why it exists (a provider exposing a second, bridged path to the
  same physical device).
- How `derived_from` distinguishes it from a natively discovered protocol.
- The consequence for output protocol selection and for Sendspin `active_source` filtering
  (cross-link Phase 5).

## Output protocol selection

- The **active output protocol is released when the session ends** (#4937).
- **Disabled linked protocols** are surfaced from and recovered via config (#3993), and universal
  player creation is skipped when the cached parent is disabled.
- #4419 ("Don't switch a playing group's output protocol when joining") — verify whether the
  doc's selection rules need this caveat.

## Pairing and setup

Protocol players can require pairing or setup before they are usable. Document that `needs_setup`
blocks availability, and cross-link the setup flow engine (Phase 3) and the player-model
setup-flow surface (Phase 4). Driving PRs: #4952, #5010, #5034.

## Participating providers

- **AirPlay was rearchitected.** The `providers/airplay/protocols/` directory (with
  `_protocol.py`, `airplay2.py`, `raop.py`) was **deleted**. The architecture is now `player.py` +
  `control_player.py` + `sendspin_bridge.py` plus pairing/setup flows. Fix any doc reference to
  the protocols split.
- **`local_audio`** lost its `player.py` and now exposes local soundcards as visible
  Sendspin-bridge players; it depends on `sendspin`.
- **`plex_connect`** lost `player_remote.py`.
- New native player providers worth a brief mention (they mostly affect identifier population
  rather than core architecture): `amplipi`, `bose_soundtouch`, `samsung_wam`, `yandex_station`,
  `ariacast_receiver`, `msx_bridge`, `teddycloud`. Keep this to a short paragraph — Phase 15 owns
  the discovery matrix.
- **Persistence:** add the persisted `CONF_REPORTED_MAC` config key.
- Check `music_assistant/models/player_provider.py` for changes to the `PlayerProvider` base
  contract and reflect anything material.

## Verification

- `rg "derived_from|_check_merge_universal_players|_update_universal_device_info|CONF_REPORTED_MAC"`.
- Confirm `providers/airplay/protocols/` really is gone.
- `pre-commit run --all-files`; diff touches only `docs/architecture/`.

## Commit

```
docs(architecture): derived transports, universal player retention, protocol release

Phase 6 of the upstream/dev refresh.
```

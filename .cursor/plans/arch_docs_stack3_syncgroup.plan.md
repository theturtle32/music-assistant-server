---
name: arch_docs_stack3_syncgroup
overview: "Refresh docs/architecture/06-grouping.md and docs/architecture/04-player-controller.md to cover upstream sync-group rework: protocol awareness + transition guards (#3600), state derivation + lifecycle handling (#3709, #3682), join/unjoin forwarding (#3718), sync leader child state forwarding (#3717), stale-state ungroup fix (#3540), removal of protocol player power control forwarding (#3659), the muted-player-in-group fix (#3655), and group member state reporting fixes (#3646, #3672)."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-syncgroup-update from docs/architecture-controller-update
    status: pending
  - id: implement
    content: Apply the doc edits per the pre-flight sub-plan
    status: pending
  - id: verify
    content: pre-commit + sweep
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture-controller-update
    status: pending
isProject: false
---

# Stack 3 — Sync group rework

## Scope (preliminary)

- **[docs/architecture/06-grouping.md](docs/architecture/06-grouping.md):** Refresh the sync-group section to cover:
  - Protocol awareness + transition guards (#3600).
  - State derivation + lifecycle handling (#3709, #3682) — corrected derivation of group state from members; tightened lifecycle for AirPlay late-joiner sync.
  - Join/unjoin forwarding (#3718) — `cmd_set_members` on a syncgroup forwards to the syncgroup player.
  - Sync leader child state forwarding (#3717).
  - Stale-state ungroup fix (#3540).
- **[docs/architecture/04-player-controller.md](docs/architecture/04-player-controller.md):**
  - Removal of protocol player power control forwarding (#3659).
  - Mute fix in group context (#3655).
  - Group member state reporting (#3646, #3672).

## Branch

Cut `docs/architecture-syncgroup-update` from `docs/architecture-controller-update`.

```bash
git fetch origin
git checkout docs/architecture-controller-update
git pull --ff-only origin docs/architecture-controller-update
git checkout -b docs/architecture-syncgroup-update
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

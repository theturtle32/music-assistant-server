---
name: arch_docs_stack6_queues
overview: "Refresh docs/architecture/09-player-queues.md to cover the upstream player_queues rewrite (~1007 lines changed): dynamic playlist queue (#3527, #3432, #3675), play-action lock (#3557, #3624), delete_item mutation safety (#3551), enqueue actions (#3753, #3663), queue restore (#3827, #3668)."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-queues-update from docs/architecture-syncgroup-update
    status: pending
  - id: implement
    content: Apply the doc edits per the pre-flight sub-plan
    status: pending
  - id: verify
    content: pre-commit + sweep
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture-syncgroup-update
    status: pending
isProject: false
---

# Stack 6 — Player queues + dynamic playlists

## Scope (preliminary)

[music_assistant/controllers/player_queues.py](music_assistant/controllers/player_queues.py) saw ~1007 lines of changes. Update [docs/architecture/09-player-queues.md](docs/architecture/09-player-queues.md):

- **Dynamic playlist queue** (#3527, #3432) — new section folded into 09 for `is_dynamic` playlist queueing, refill behavior, and how unplayed buffered tracks are preserved (#3675).
- **Concurrency model:** `play_action_in_progress` lock (#3557), simultaneous play action deadlock fix (#3624), `delete_item` mutation safety (#3551).
- **Enqueue actions:** `replace` no longer stops the music (#3753); play-from-here respects sort order (#3663).
- **Queue restore:** `from_cache` reconstructs `radio_source` and `enqueued_media_items` (#3827); zero-duration item fix (#3668).

Hybrid strategy applied: dynamic playlists folds in (it's logically a queue feature), no new file.

## Branch

Cut `docs/architecture-queues-update` from `docs/architecture-syncgroup-update` (depends on the player controller chain).

```bash
git fetch origin
git checkout docs/architecture-syncgroup-update
git pull --ff-only origin docs/architecture-syncgroup-update
git checkout -b docs/architecture-queues-update
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

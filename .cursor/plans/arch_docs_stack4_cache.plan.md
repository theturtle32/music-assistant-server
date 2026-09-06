---
name: arch_docs_stack4_cache
overview: "Refresh docs/architecture/ to reflect the cache controller package split (cache.py -> cache/{controller,helpers,constants,__init__}.py + README.md), update path references, and cross-link to the new in-tree music_assistant/controllers/cache/README.md. Includes a brief mention of the JSON serialization consistency fix (#3542)."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-cache-split from docs/architecture
    status: pending
  - id: implement
    content: Apply the doc edits per the pre-flight sub-plan
    status: pending
  - id: verify
    content: pre-commit + sweep
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture
    status: pending
isProject: false
---

# Stack 4 — Cache controller package split

## Scope (preliminary)

- Path-reference audit: any mention of `music_assistant/controllers/cache.py` in docs/architecture must point at `music_assistant/controllers/cache/controller.py` instead. Audit via `rg cache.py docs/architecture`.
- Cross-link to in-tree [music_assistant/controllers/cache/README.md](music_assistant/controllers/cache/README.md) wherever caching is discussed.
- Brief mention of the JSON serialization consistency fix (#3542) if any doc describes cache value semantics.
- Likely-affected files: [docs/architecture/00-overview.md](docs/architecture/00-overview.md), [docs/architecture/02-configuration.md](docs/architecture/02-configuration.md), and any of the per-subsystem docs that name `cache.py`.

## Branch

Cut `docs/architecture-cache-split` from `docs/architecture` (independent — no parent).

```bash
git fetch origin
git checkout docs/architecture
git pull --ff-only origin docs/architecture
git checkout -b docs/architecture-cache-split
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

---
name: arch_docs_stack5_metadata
overview: "Refresh docs/architecture/14-metadata.md to cover the upstream metadata controller rewrite: provider priority (#3623), iTunes artwork provider (#3740), artist artwork display for radio streams (#3110), opt-out for radio artwork lookup (#3741), local-only genre metadata option (#3815), TODO cleanup (#3771), caching fixes."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-metadata-update from docs/architecture
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

# Stack 5 — Metadata controller rewrite

## Scope (preliminary)

[music_assistant/controllers/metadata.py](music_assistant/controllers/metadata.py) saw +744 lines of upstream changes since the docs were originally written. Update [docs/architecture/14-metadata.md](docs/architecture/14-metadata.md) for:

- Metadata provider priority (#3623) — explicit ordering when multiple providers can supply metadata.
- iTunes artwork metadata provider (#3740) — new provider type.
- Artist artwork display for radio streams (#3110) — new lookup behavior.
- Opt-out config entry for radio artwork lookup (#3741).
- Local-only genre metadata option (#3815).
- Cleanup of TODOs (#3771) — verify what landed and incorporate.
- Caching fixes (84d5db95) — clarify cache layering with the new cache package (cross-link to Stack 4 if both have landed).

## Branch

Cut `docs/architecture-metadata-update` from `docs/architecture` (independent — no parent).

```bash
git fetch origin
git checkout docs/architecture
git pull --ff-only origin docs/architecture
git checkout -b docs/architecture-metadata-update
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

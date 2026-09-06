---
name: arch_docs_stack8_misc
overview: "Catch-all PR for smaller upstream changes that don't justify their own stack level: discovery doc updates (Sendspin manual IPs, AirPlay race fix, Cast restart), short mentions of new plugin providers (Yandex Smart Home, Yandex Music Connect, NTS Radio), and a final stale-reference rg sweep across docs/architecture."
todos:
  - id: preflight
    content: "Pre-flight: switch to Plan mode and write a detailed sub-plan for this stack against current upstream/dev (file paths, code citations, exact wording)"
    status: pending
  - id: branch
    content: Cut docs/architecture-misc-cleanup from docs/architecture
    status: pending
  - id: implement
    content: Apply the doc edits per the pre-flight sub-plan
    status: pending
  - id: verify
    content: pre-commit + final stale-reference rg sweep across the whole tree
    status: pending
  - id: commit_pr
    content: Single commit, push, open PR -> docs/architecture
    status: pending
isProject: false
---

# Stack 8 — Misc subsystems cleanup

## Scope (preliminary)

The catch-all PR for smaller items that don't justify their own stack level:

- **[docs/architecture/13-discovery.md](docs/architecture/13-discovery.md):** Sendspin manual IP addresses setting (#3846); AirPlay mDNS discovery race fix (#3546); Chromecast player disappearing fix (#3758) — all if they affect documented discovery behavior.
- **[docs/architecture/11-plugin-system.md](docs/architecture/11-plugin-system.md):** New plugin providers (Yandex Smart Home #3615, Yandex Music Connect/Ynison #3614, NTS Radio music provider #3722) — short mentions in the providers list, not deep coverage.
- **[docs/architecture/00-overview.md](docs/architecture/00-overview.md):** Update any feature lists or version notes if they exist.
- Final `rg` sweep for stale path references and any remaining `volume_set_optimistic`-style ghosts.

## Branch

Cut `docs/architecture-misc-cleanup` from `docs/architecture` (independent — no parent).

```bash
git fetch origin
git checkout docs/architecture
git pull --ff-only origin docs/architecture
git checkout -b docs/architecture-misc-cleanup
```

## Pre-flight planning step

When you hit Build on this skeleton:

1. The agent enters Plan mode and re-reads the relevant upstream code paths and current doc state.
2. It produces a focused sub-plan with concrete file paths, line numbers, and exact wording for the new content.
3. After you approve the sub-plan, the agent switches to Agent mode and executes the rest of the todos.

This deferral lets the detailed plan reflect any drift in `upstream/dev` between now and the time this stack is built.

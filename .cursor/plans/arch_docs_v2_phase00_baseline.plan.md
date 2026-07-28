---
name: arch_docs_v2_phase00_baseline
overview: "Phase 0 of the round-2 architecture docs refresh. Fast-forward origin/dev to upstream/dev (1096 commits), cut docs/architecture-refresh from docs/architecture, merge the new dev baseline in, and open the single PR into docs/architecture that all later phases will grow. No doc edits in this phase."
todos:
  - id: fetch
    content: "Fetch upstream and origin; confirm upstream/dev tip and that the current docs/architecture base (4b67568d6) is an ancestor of it"
    status: pending
  - id: ff_dev
    content: "Fast-forward origin/dev to upstream/dev and push"
    status: pending
  - id: branch
    content: "Check out docs/architecture-refresh (already created, carrying the plan-stack commit)"
    status: pending
  - id: merge
    content: "Merge origin/dev into docs/architecture-refresh; resolve any conflicts (expected: none)"
    status: pending
  - id: sanity
    content: "Sanity-check the merged tree: docs/architecture/ intact, controller packages present, pre-commit passes"
    status: pending
  - id: pr
    content: "Push the branch and open the PR into docs/architecture with the phase checklist as its body"
    status: pending
  - id: cleanup
    content: "Remove the /tmp/ma-dev scratch worktree if one exists, since the working tree is now current dev"
    status: pending
isProject: false
---

# Phase 0 — Baseline sync and PR setup

No documentation is edited in this phase. The goal is to get the code being documented into the
working tree, so that every later phase can read `music_assistant/` directly instead of
inspecting `upstream/dev` from a side worktree.

## Current state

- `docs/architecture` = 10 commits on top of upstream `4b67568d6` ("Fix protocol recovery with
  missing cached parent (#3829)"), 2 of which are the docs tree and the round-1 plan stack, 8 of
  which are the round-1 refresh squashes.
- `upstream/dev` = `76422b305`, **1096 commits ahead**. `4b67568d6` is a clean ancestor, so the
  fast-forward is safe.
- `origin/dev` (the fork's `dev`) is stale at the old baseline.
- PR #6 (`docs/architecture` → `dev`, fork) is open and stays open.
- **`docs/architecture-refresh` already exists** on `origin`, cut from `docs/architecture` and
  carrying one commit: the round-2 plan stack. So this phase checks it out rather than creating it,
  and the baseline merge becomes the branch's second commit. No PR has been opened yet.

## Steps

```bash
cd /Users/theturtle32/work/music-assistant-server
git fetch upstream dev
git fetch origin

# Confirm the fast-forward is safe before doing anything.
git merge-base --is-ancestor 4b67568d6 upstream/dev && echo "ff safe"

# Fast-forward the fork's dev to upstream/dev.
git push origin upstream/dev:refs/heads/dev

# The long-lived refresh branch already exists with the plan-stack commit.
git checkout docs/architecture-refresh
git pull --ff-only origin docs/architecture-refresh

# Bring the new code baseline in.
git fetch origin dev
git merge origin/dev
```

The merge is expected to be conflict-free: `docs/` does not exist upstream, and `.cursor/plans/`
is fork-only. If conflicts do appear, they will be in fork-only files — keep the fork side for
`docs/` and `.cursor/plans/`, take upstream for everything under `music_assistant/` and `tests/`.

## Sanity checks before opening the PR

- `ls docs/architecture/` still lists `00-overview.md` … `16-audio-analysis.md` and `README.md`.
- The new controller packages are present, confirming the merge landed:
  `music_assistant/controllers/config/`, `controllers/music/`, `controllers/metadata/`,
  `controllers/player_queues/`, `controllers/dashboard/`, `controllers/diagnostics/`,
  `controllers/translations/`.
- `git log --oneline -3` shows the merge commit with `docs/architecture` and `origin/dev` as parents.
- `pre-commit run --all-files` passes. If upstream hooks fail on upstream-owned files, do not
  "fix" upstream code in this branch — note it and move on.

## PR

Open **one** PR that every later phase will add commits to:

```bash
git push origin docs/architecture-refresh
gh pr create -R theturtle32/music-assistant-server \
  --base docs/architecture \
  --title "docs(architecture): refresh against current upstream/dev" \
  --body-file -   # see body below
```

PR body should contain the phase checklist from `arch_docs_v2_index.plan.md` (phases 0–16) as
unchecked boxes, so progress is visible as commits land. Note in the body that the first commit
is a baseline merge of 1096 upstream commits and carries no doc changes, so reviewers should
review the PR by commit rather than by combined diff.

## Cleanup

If a scratch worktree at `/tmp/ma-dev` exists from the planning pass, remove it — the working
tree is now the authoritative copy of current `dev`:

```bash
git worktree remove /tmp/ma-dev --force
git worktree prune
```

## Note for later phases

After this phase, `git log --oneline 4b67568d6..HEAD -- <path>` is the way to find the upstream
PRs behind any given change, and code can be read straight from the working tree.

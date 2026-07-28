---
name: arch_docs_v2_phase00_baseline
overview: "COMPLETE. Phase 0 of the round-2 architecture docs refresh: sync the fork's dev to upstream/dev (1096 commits), merge that baseline into both the docs branch and the refresh branch stacked on it, and open the single PR that all later phases will grow. No doc edits in this phase. Final branch names are docs/arch and docs/arch-refresh; see Outcome at the end for what actually happened."
todos:
  - id: fetch
    content: Fetch upstream and origin; confirm upstream/dev tip and that the current docs/architecture base (4b67568d6) is an ancestor of it
    status: completed
  - id: ff_dev
    content: Fast-forward origin/dev to upstream/dev and push
    status: completed
  - id: branch
    content: Check out docs/architecture-refresh (already created, carrying the plan-stack commit)
    status: completed
  - id: merge
    content: "Merge origin/dev into docs/architecture-refresh; resolve any conflicts (expected: none)"
    status: completed
  - id: sanity
    content: "Sanity-check the merged tree: docs/architecture/ intact, controller packages present, pre-commit passes"
    status: completed
  - id: pr
    content: Push the branch and open the PR into docs/architecture with the phase checklist as its body
    status: completed
  - id: cleanup
    content: Remove the /tmp/ma-dev scratch worktree if one exists, since the working tree is now current dev
    status: completed
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

## Outcome

Completed, with three deviations from the plan above. The names and numbers below are the current
ones; the `docs/architecture*` names used earlier in this file are dead.

**Branches were renamed.** `docs/architecture` collided with the `docs/architecture/` directory,
which makes bare git revision arguments ambiguous — `git reset --hard docs/architecture` fails with
"ambiguous argument" and silently does nothing useful. Final names:

| Role | Branch |
| --- | --- |
| Docs base branch, submitted upstream | `docs/arch` |
| Long-lived refresh branch, one commit per phase | `docs/arch-refresh` |

Renaming via the GitHub API auto-closed the two open PRs, because GitHub treats a renamed head
branch as deleted and closed PRs cannot be reopened once the head is gone. They were recreated:

| Old | New | Shape |
| --- | --- | --- |
| #6 | **#17** | `docs/arch` → `dev` |
| #16 | **#18** | `docs/arch-refresh` → `docs/arch` |

**`upstream/dev` was merged into the base branch too.** The plan only merged it into the refresh
branch, which left the refresh PR showing all 1096 upstream commits. GitHub diffs against the merge
base, so the base branch must also contain upstream for a stacked PR to read as documentation-only.
`docs/arch` therefore carries its own merge (`ba9adaf8e`) and `docs/arch-refresh` was rebuilt on top
of it carrying only the plan commits. PR #18 is now 18 files, 2848 insertions, 0 deletions.

**The fork's `dev` was already current.** The plan assumed `origin/dev` was stale; it was already at
`76422b305`, verified with `git ls-remote` against both remotes. Something auto-syncs the fork, so
the fast-forward was a no-op.

### Known issue for later phases

`pre-commit run --all-files` fails its **mypy** hook with ~140 errors across 42 upstream-owned
files. This is a stale local venv, not a code problem: `aiosendspin` 5.1.1 is installed while the
merged tree requires 7.0.0, so mypy sees a library missing methods the new code calls. All 26 other
hooks pass (`SKIP=mypy pre-commit run --all-files` is green). Running `scripts/setup.sh` fixes it but
reinstalls a large dependency set. Do not "fix" upstream code to satisfy mypy.

### Loose ends, deliberately not addressed

- A local `backup/refresh-pre-restructure` ref points at the pre-rebuild tip of the refresh branch.
  Safe to delete once PR #18 looks right.
- PR #17 carries 9 round-1 `.cursor/plans/*.plan.md` files, and `docs/architecture/plans/` holds 10
  more verification reports and sub-plans. These are working notes, not architecture documentation,
  and probably should not go upstream. Stripping them is a separate decision.

"""
Keep the architecture docs and the in-tree README files honest about what they link to.

The script has two modes. Link validation walks every documentation file and fails when a link
points at a repository path that does not exist, which catches a doc left behind by a rename.
The reference report takes the source files being committed and prints the documents that
describe them, so the author (human or agent) knows where to look when behaviour changed. The
report never fails; it only tells you where to look.

A document "describes" a source file when it links to that file, when it links to a directory
containing it, or when it is the nearest README next to it.

Usage:
    uv run -m scripts.check_doc_references                      # validate every link
    uv run -m scripts.check_doc_references --report FILE...     # list docs describing FILEs
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

# ruff: noqa: T201

# repo paths (this file lives at <repo>/scripts/check_doc_references.py)
REPO_ROOT = Path(__file__).resolve().parents[1]

# only paths below this are indexed and reported on; the shipped package is what docs describe
PACKAGE_PREFIX = "music_assistant/"

# directories a filesystem walk must never descend into; the git listing excludes them already
UNTRACKED_DIRS = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__", "site"})

# Links to the canonical repository resolve to a path inside this checkout.
GITHUB_BLOB_PATTERN = re.compile(
    r"^https://github\.com/music-assistant/server/(?:blob|tree)/[^/]+/(?P<path>.+)$"
)
INLINE_LINK_PATTERN = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
REFERENCE_LINK_PATTERN = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?(\S+)>?", re.MULTILINE)
CODE_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")
# a backtick run and everything up to its matching run; `def f[T](...)` is not a link
INLINE_CODE_PATTERN = re.compile(r"(?<!`)(`+)(?!`).*?(?<!`)\1(?!`)")

# Schemes and targets that are not repository paths.
EXTERNAL_PREFIXES = ("http://", "https://", "mailto:", "tel:", "data:", "//")


def find_broken_links() -> dict[str, list[str]]:
    """Return ``{repo-relative doc path: [messages]}`` for every link to a missing repo path."""
    broken: dict[str, list[str]] = {}
    for doc in iter_doc_files():
        rel_doc = doc.relative_to(REPO_ROOT).as_posix()
        for lineno, target in _iter_links(doc):
            resolved = _resolve_target(doc, target)
            if resolved is None or resolved.exists():
                continue
            missing = resolved.relative_to(REPO_ROOT).as_posix()
            broken.setdefault(rel_doc, []).append(
                f"{rel_doc}:{lineno}: link target does not exist: {missing}"
            )
    return broken


def build_reference_index() -> dict[str, set[str]]:
    """
    Return ``{repo-relative linked path: {doc paths}}`` for every link into the package.

    Both files and directories appear as keys; :func:`docs_for_source` expands a directory key to
    the files below it.
    """
    index: dict[str, set[str]] = {}
    for doc in iter_doc_files():
        rel_doc = doc.relative_to(REPO_ROOT).as_posix()
        for _lineno, target in _iter_links(doc):
            resolved = _resolve_target(doc, target)
            if resolved is None or not resolved.exists():
                continue
            rel_target = resolved.relative_to(REPO_ROOT).as_posix()
            if not rel_target.startswith(PACKAGE_PREFIX):
                continue
            index.setdefault(rel_target, set()).add(rel_doc)
    return index


def docs_for_source(source: str, index: dict[str, set[str]]) -> list[str]:
    """
    Return the documents that describe a source file, co-located ones first.

    Every markdown file sitting beside the source counts as describing it, which is what makes a
    deep dive discoverable without it having to link the module by name.

    :param source: Repo-relative path of the source file.
    :param index: The mapping returned by :func:`build_reference_index`.
    """
    linked: set[str] = set()
    for candidate in [source, *_ancestors(source)]:
        linked |= index.get(candidate, set())
    colocated = _colocated_docs(source)
    return [*colocated, *sorted(linked.difference(colocated))]


def iter_doc_files() -> list[Path]:
    """
    Return every markdown file in the repository.

    Uses the git index so ignored trees such as ``.venv`` are skipped, and falls back to a
    filtered walk when git is unavailable.
    """
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-z", "*.md"],  # noqa: S607
            capture_output=True,
            check=True,
            cwd=REPO_ROOT,
            text=True,
        ).stdout
    except OSError, subprocess.CalledProcessError:
        return sorted(_walk_markdown(REPO_ROOT))
    return sorted(REPO_ROOT / name for name in listed.split("\0") if name)


def main(argv: list[str] | None = None) -> int:
    """
    Validate documentation links, or report the docs describing the given source files.

    :param argv: Optional argument vector; pass ``--report`` followed by source paths to run the
        reference report instead of link validation.
    """
    argv = sys.argv[1:] if argv is None else argv
    if "--report" in argv:
        return _report(argv[argv.index("--report") + 1 :])
    broken = find_broken_links()
    if not broken:
        return 0
    print("Documentation links point at paths that no longer exist:")
    for path in sorted(broken):
        for message in broken[path]:
            print(f"  {message}")
    return 1


def _report(sources: list[str]) -> int:
    """
    Print the documents describing each source file; always succeeds.

    :param sources: Repo-relative paths of the source files being committed.
    """
    interesting = [src for src in sources if src.startswith(PACKAGE_PREFIX)]
    if not interesting:
        return 0
    index = build_reference_index()
    described = {src: docs_for_source(src, index) for src in sorted(interesting)}
    described = {src: docs for src, docs in described.items() if docs}
    if not described:
        return 0
    print("These files are described by documentation; update it if the behaviour changed:")
    for src, docs in described.items():
        print(f"  {src}")
        for doc in docs:
            print(f"      {doc}")
    return 0


def _iter_links(doc: Path) -> list[tuple[int, str]]:
    """
    Return ``(lineno, target)`` for every markdown link in a document, ignoring code blocks.

    :param doc: Absolute path of the markdown file to read.
    """
    try:
        text = doc.read_text(encoding="utf-8")
    except OSError:
        return []
    links: list[tuple[int, str]] = []
    in_fence = False
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        if CODE_FENCE_PATTERN.match(raw_line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = INLINE_CODE_PATTERN.sub("", raw_line)
        for match in INLINE_LINK_PATTERN.finditer(line):
            links.append((lineno, match.group(1)))
        for match in REFERENCE_LINK_PATTERN.finditer(line):
            links.append((lineno, match.group(1)))
    return links


def _resolve_target(doc: Path, target: str) -> Path | None:
    """
    Return the repository path a link points at, or ``None`` when it is not a repository path.

    :param doc: Absolute path of the document holding the link, used to resolve relative targets.
    :param target: The raw link target as written in the markdown.
    """
    target = target.strip()
    if not target or target.startswith("#"):
        return None
    from_repo_root = False
    if github_match := GITHUB_BLOB_PATTERN.match(target):
        target = github_match.group("path")
        from_repo_root = True
    elif target.startswith(EXTERNAL_PREFIXES):
        return None
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    if not path_part:
        return None
    if path_part.startswith("/"):
        from_repo_root = True
    base = REPO_ROOT if from_repo_root else doc.parent
    resolved = (base / path_part.lstrip("/")).resolve()
    if not resolved.is_relative_to(REPO_ROOT):
        return None
    return resolved


def _walk_markdown(root: Path) -> list[Path]:
    """Return the markdown files under a directory, skipping trees git would ignore."""
    found: list[Path] = []
    for path in root.iterdir():
        if path.is_dir():
            if path.name not in UNTRACKED_DIRS:
                found.extend(_walk_markdown(path))
        elif path.suffix == ".md":
            found.append(path)
    return found


def _colocated_docs(source: str) -> list[str]:
    """
    Return the markdown files sitting in a source file's own directory, README first.

    :param source: Repo-relative path of the source file.
    """
    directory = REPO_ROOT / source
    parent = directory.parent
    if not parent.is_dir():
        return []
    names = sorted(path.name for path in parent.glob("*.md"))
    if "README.md" in names:
        names.remove("README.md")
        names.insert(0, "README.md")
    rel_parent = parent.relative_to(REPO_ROOT).as_posix()
    return [f"{rel_parent}/{name}" for name in names if f"{rel_parent}/{name}" != source]


def _ancestors(source: str) -> list[str]:
    """Return the directories containing a source file, nearest first, down to the package root."""
    parts = source.split("/")
    return ["/".join(parts[:depth]) for depth in range(len(parts) - 1, 0, -1)]


if __name__ == "__main__":
    raise SystemExit(main())

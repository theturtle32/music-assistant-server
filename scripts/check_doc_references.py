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

    Asks git rather than walking, so ignored trees such as ``.venv`` are skipped. Untracked files
    are included, so a doc that has been written but not yet staged is still checked. Falls back
    to a filtered walk when git is unavailable.
    """
    try:
        listed = subprocess.run(
            # --others with --exclude-standard adds untracked files without adding ignored ones
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "*.md"],  # noqa: S607
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
    Print the documents describing the given source files; always succeeds.

    Grouped by document rather than by file: the document is what the reader has to go and
    update, and a package whose whole directory was touched would otherwise repeat its README
    once per file.

    :param sources: Repo-relative paths of the source files being committed.
    """
    interesting = [src for src in sources if _is_reportable(src)]
    if not interesting:
        return 0
    index = build_reference_index()
    described: dict[str, list[str]] = {}
    for src in sorted(set(interesting)):
        for doc in docs_for_source(src, index):
            described.setdefault(doc, []).append(src)
    if not described:
        return 0
    # sibling docs in one package all describe the same files, so documents covering an
    # identical set are listed together rather than repeating that set under each of them
    grouped: dict[tuple[str, ...], list[str]] = {}
    for doc, srcs in described.items():
        grouped.setdefault(tuple(srcs), []).append(doc)
    print("These documents describe the files being committed; update them if behaviour changed:")
    # most-affected group first, so the documents to start with are at the top
    for srcs, docs in sorted(grouped.items(), key=lambda kv: (-len(kv[0]), kv[1][0])):
        for doc in sorted(docs):
            print(f"  {doc}")
        for index, line in enumerate(_describe_sources(list(srcs))):
            print(f"      {'for ' if index == 0 else '    '}{line}")
    return 0


def _is_reportable(source: str) -> bool:
    """
    Return whether a path is a package source file worth reporting on.

    Directories and build artefacts are skipped: a caller expanding a glob passes them in, and
    neither is something a document describes.

    :param source: Repo-relative path handed to the report.
    """
    if not source.startswith(PACKAGE_PREFIX) or "__pycache__" in source.split("/"):
        return False
    return (REPO_ROOT / source).is_file()


def _describe_sources(sources: list[str]) -> list[str]:
    """
    Return display lines for the source files a document describes, folded by directory.

    :param sources: Repo-relative paths, already sorted.
    """
    by_directory: dict[str, list[str]] = {}
    for src in sources:
        directory, _, name = src.rpartition("/")
        by_directory.setdefault(directory, []).append(name)
    lines = []
    for directory, names in by_directory.items():
        if len(names) == 1:
            lines.append(f"{directory}/{names[0]}")
            continue
        lines.append(f"{directory}/")
        lines += [f"  {chunk}" for chunk in _wrap(names)]
    return lines


def _wrap(names: list[str], width: int = 88) -> list[str]:
    """
    Return comma-separated names packed into lines no wider than ``width``.

    :param names: File names to join.
    :param width: Maximum line length before wrapping.
    """
    lines: list[str] = []
    current = ""
    for name in names:
        candidate = f"{current}, {name}" if current else name
        if current and len(candidate) > width:
            lines.append(f"{current},")
            current = name
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


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

"""Tests for the documentation reference check."""

from pathlib import Path

import pytest

from scripts import check_doc_references
from scripts.check_doc_references import (
    build_reference_index,
    docs_for_source,
    find_broken_links,
    iter_doc_files,
    main,
)


@pytest.fixture(name="repo")
def repo_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the check at a throwaway repository layout and return its root."""
    (tmp_path / "docs" / "architecture").mkdir(parents=True)
    (tmp_path / "music_assistant" / "controllers" / "players").mkdir(parents=True)
    monkeypatch.setattr(check_doc_references, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(check_doc_references, "DOCS_ROOT", tmp_path / "docs")
    monkeypatch.setattr(check_doc_references, "PACKAGE_ROOT", tmp_path / "music_assistant")
    return tmp_path


def _write(repo: Path, relative: str, text: str = "") -> Path:
    """Create a file inside the throwaway repository."""
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_existing_relative_link_passes(repo: Path) -> None:
    """A relative link to a file that exists is not reported."""
    _write(repo, "music_assistant/controllers/players/controller.py")
    _write(repo, "docs/architecture/grouping.md", "See [it](../../music_assistant/controllers/)")
    assert find_broken_links() == {}


def test_missing_relative_link_is_reported(repo: Path) -> None:
    """A relative link to a path that does not exist is reported with its line number."""
    _write(repo, "docs/architecture/grouping.md", "\nSee [gone](../../music_assistant/nope.py)\n")
    broken = find_broken_links()
    assert list(broken) == ["docs/architecture/grouping.md"]
    assert "grouping.md:2" in broken["docs/architecture/grouping.md"][0]


def test_github_blob_url_resolves_to_repo_path(repo: Path) -> None:
    """A canonical GitHub blob URL is checked against the local checkout."""
    base = "https://github.com/music-assistant/server/blob/dev/music_assistant"
    _write(repo, "docs/architecture/players.md", f"[here]({base}/controllers/players/README.md)")
    assert list(find_broken_links()) == ["docs/architecture/players.md"]
    _write(repo, "music_assistant/controllers/players/README.md")
    assert find_broken_links() == {}


def test_tree_url_and_anchors_and_queries_are_stripped(repo: Path) -> None:
    """Tree URLs resolve like blob URLs, and anchors or queries are ignored."""
    base = "https://github.com/music-assistant/server/tree/dev/music_assistant/controllers"
    _write(repo, "music_assistant/controllers/players/README.md", "# Players")
    _write(
        repo,
        "docs/architecture/players.md",
        f"[dir]({base}) and [anchor](../../music_assistant/controllers/players/README.md#layout)",
    )
    assert find_broken_links() == {}


def test_external_links_are_ignored(repo: Path) -> None:
    """Links to other sites, mail addresses and bare anchors are not repository paths."""
    _write(
        repo,
        "docs/architecture/overview.md",
        "[site](https://music-assistant.io/x) [mail](mailto:a@b.c) [top](#heading)",
    )
    assert find_broken_links() == {}


def test_links_inside_code_fences_are_ignored(repo: Path) -> None:
    """A markdown link inside a fenced code block is an example, not a link."""
    _write(
        repo,
        "docs/architecture/overview.md",
        "```\n[example](../../music_assistant/nope.py)\n```\n",
    )
    assert find_broken_links() == {}


def test_image_and_reference_links_are_checked(repo: Path) -> None:
    """Image targets and reference-style definitions are validated too."""
    _write(repo, "docs/architecture/overview.md", "![diagram](missing.png)\n\n[ref]: other.md\n")
    messages = find_broken_links()["docs/architecture/overview.md"]
    assert len(messages) == 2


def test_readmes_are_scanned_as_documents(repo: Path) -> None:
    """In-tree README files are part of the document set the check owns."""
    _write(repo, "music_assistant/controllers/players/README.md", "[gone](./missing.py)")
    assert [path.name for path in iter_doc_files()] == ["README.md"]
    assert list(find_broken_links()) == ["music_assistant/controllers/players/README.md"]


def test_index_maps_linked_package_paths_to_docs(repo: Path) -> None:
    """The inverse index records which documents link to which package paths."""
    _write(repo, "music_assistant/controllers/players/controller.py")
    _write(
        repo,
        "docs/architecture/grouping.md",
        "[file](../../music_assistant/controllers/players/controller.py)",
    )
    assert build_reference_index() == {
        "music_assistant/controllers/players/controller.py": {"docs/architecture/grouping.md"}
    }


def test_directory_link_covers_files_below_it(repo: Path) -> None:
    """A document linking a directory describes the files inside it."""
    _write(repo, "music_assistant/controllers/players/controller.py")
    _write(
        repo,
        "docs/architecture/grouping.md",
        "[dir](../../music_assistant/controllers/players/)",
    )
    index = build_reference_index()
    docs = docs_for_source("music_assistant/controllers/players/controller.py", index)
    assert docs == ["docs/architecture/grouping.md"]


def test_nearest_readme_comes_first(repo: Path) -> None:
    """The co-located README leads the report, ahead of the linked architecture docs."""
    _write(repo, "music_assistant/controllers/players/controller.py")
    _write(repo, "music_assistant/controllers/players/README.md", "# Players")
    _write(
        repo,
        "docs/architecture/grouping.md",
        "[dir](../../music_assistant/controllers/players/)",
    )
    docs = docs_for_source(
        "music_assistant/controllers/players/controller.py", index=build_reference_index()
    )
    assert docs == [
        "music_assistant/controllers/players/README.md",
        "docs/architecture/grouping.md",
    ]


def test_report_mode_never_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The reference report prints what it found and exits zero."""
    _write(repo, "music_assistant/controllers/players/controller.py")
    _write(repo, "music_assistant/controllers/players/README.md", "# Players")
    assert main(["--report", "music_assistant/controllers/players/controller.py"]) == 0
    assert "players/README.md" in capsys.readouterr().out


@pytest.mark.usefixtures("repo")
def test_report_ignores_files_outside_the_package() -> None:
    """Paths outside music_assistant have no co-located documentation to report."""
    assert main(["--report", "scripts/check_doc_references.py"]) == 0


def test_main_returns_one_when_a_link_is_broken(repo: Path) -> None:
    """Link validation is the failing mode of the check."""
    _write(repo, "docs/architecture/overview.md", "[gone](../../music_assistant/nope.py)")
    assert main([]) == 1

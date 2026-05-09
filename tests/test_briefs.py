from pathlib import Path

from agent_inbox import briefs


def test_load_agents_empty(tmp_path: Path) -> None:
    assert briefs.load_agents(tmp_path) == set()


def test_load_agents_picks_up_md_files(tmp_path: Path) -> None:
    (tmp_path / "alice.md").write_text("# Alice\n")
    (tmp_path / "bob.md").write_text("# Bob\n")
    assert briefs.load_agents(tmp_path) == {"alice", "bob"}


def test_load_agents_skips_reserved(tmp_path: Path) -> None:
    (tmp_path / "all.md").write_text("# Reserved\n")
    (tmp_path / "alice.md").write_text("# Alice\n")
    assert briefs.load_agents(tmp_path) == {"alice"}


def test_load_agents_skips_invalid_names(tmp_path: Path) -> None:
    (tmp_path / "1bad.md").write_text("starts with digit — rejected")
    (tmp_path / "with spaces.md").write_text("spaces — rejected")
    (tmp_path / "has.dots.md").write_text("dots — rejected (single dot would split stem)")
    (tmp_path / "good.md").write_text("ok")
    (tmp_path / "good-2.md").write_text("hyphens and digits ok after first char")
    agents = briefs.load_agents(tmp_path)
    assert agents == {"good", "good-2"}


def test_load_agents_lowercases_filenames(tmp_path: Path) -> None:
    (tmp_path / "Alice.md").write_text("# Alice")
    agents = briefs.load_agents(tmp_path)
    assert agents == {"alice"}


def test_name_regex_uses_strict_end_of_string() -> None:
    """Python's `$` matches before a final `\\n` by default. We use `\\Z`
    so a name with a trailing newline is rejected — matches Go's
    stricter `regexp` and the documented contract."""
    assert briefs.NAME_RE.match("alice") is not None
    assert briefs.NAME_RE.match("good-2") is not None
    # Trailing newline is the bug `\Z` closes.
    assert briefs.NAME_RE.match("alice\n") is None
    # Other whitespace chars stay correctly rejected.
    assert briefs.NAME_RE.match("alice\r") is None
    assert briefs.NAME_RE.match("alice\t") is None
    assert briefs.NAME_RE.match("alice ") is None


def test_read_brief(tmp_path: Path) -> None:
    (tmp_path / "alice.md").write_text("# Alice\n\nReviews PRs.\n")
    assert briefs.read_brief("alice", tmp_path) == "# Alice\n\nReviews PRs.\n"
    assert briefs.read_brief("missing", tmp_path) is None

"""Tests for input validation: length caps and LIKE-pattern escaping.

These cover the v0.3.2 hardening pass:
  - subject/body length caps (disk-exhaustion guard)
  - LIKE wildcard escaping in search (literal-match correctness)
"""

from pathlib import Path

import pytest

from agent_inbox import core


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


# --- Length caps ----------------------------------------------------------


def test_subject_at_max_accepted(setup) -> None:
    s = "x" * core.MAX_SUBJECT_LEN
    sent = core.send("alice", "bob", "info", s, "")
    assert sent["status"] == "sent"


def test_subject_over_max_rejected(setup) -> None:
    s = "x" * (core.MAX_SUBJECT_LEN + 1)
    with pytest.raises(ValueError, match="Subject too long"):
        core.send("alice", "bob", "info", s, "")


def test_body_at_max_accepted(setup) -> None:
    b = "x" * core.MAX_BODY_LEN
    sent = core.send("alice", "bob", "info", "ok", b)
    assert sent["status"] == "sent"


def test_body_over_max_rejected(setup) -> None:
    b = "x" * (core.MAX_BODY_LEN + 1)
    with pytest.raises(ValueError, match="Body too long"):
        core.send("alice", "bob", "info", "ok", b)


def test_reply_body_capped(setup) -> None:
    sent = core.send("alice", "bob", "info", "topic", "")
    huge = "x" * (core.MAX_BODY_LEN + 1)
    with pytest.raises(ValueError, match="Body too long"):
        core.reply("bob", sent["id"], huge)


# --- LIKE-pattern escaping ------------------------------------------------


def test_search_percent_matches_literally(setup) -> None:
    """Without escaping, '100%' would match any 4-char string starting
    with '100'. With escaping, only subjects containing the literal '%'."""
    core.send("alice", "bob", "info", "100% complete", "")
    core.send("alice", "bob", "info", "1000 messages", "")
    core.send("alice", "bob", "info", "100x retry", "")

    result = core.search(subject="100%")
    subjects = {m["subject"] for m in result["messages"]}
    assert subjects == {"100% complete"}


def test_search_underscore_matches_literally(setup) -> None:
    core.send("alice", "bob", "info", "in_progress", "")
    core.send("alice", "bob", "info", "in progress", "")
    core.send("alice", "bob", "info", "inXprogress", "")

    result = core.search(subject="in_progress")
    subjects = {m["subject"] for m in result["messages"]}
    assert subjects == {"in_progress"}


def test_search_backslash_matches_literally(setup) -> None:
    """Backslash is the escape character; user input containing a literal
    backslash needs to be escape-doubled."""
    core.send("alice", "bob", "info", "path\\to\\file", "")
    core.send("alice", "bob", "info", "path/to/file", "")

    result = core.search(subject="path\\to")
    subjects = {m["subject"] for m in result["messages"]}
    assert subjects == {"path\\to\\file"}


def test_search_no_pattern_returns_substring_match(setup) -> None:
    """Sanity: ordinary substring search still works after the escape fix."""
    core.send("alice", "bob", "info", "release v1.0", "")
    core.send("alice", "bob", "info", "lunch tomorrow", "")
    core.send("alice", "bob", "info", "release notes", "")

    result = core.search(subject="release")
    subjects = {m["subject"] for m in result["messages"]}
    assert subjects == {"release v1.0", "release notes"}

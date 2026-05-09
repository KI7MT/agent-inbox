"""Core-level tests — exercise inbox operations through the plain-function API."""

from pathlib import Path

import pytest

from agent_inbox import core


@pytest.fixture
def briefs_and_db(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice\n")
    (briefs_dir / "bob.md").write_text("# Bob\n")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_list_agents(briefs_and_db) -> None:
    result = core.list_agents()
    assert set(result["agents"]) == {"alice", "bob"}


def test_send_check_round_trip(briefs_and_db) -> None:
    sent = core.send("alice", "bob", "info", "hi", "hello")
    assert sent["status"] == "sent"
    assert sent["initial_state"] == "unread"

    checked = core.check("bob")
    assert checked["unread_count"] == 1
    assert checked["messages"][0]["subject"] == "hi"


def test_send_to_unknown_recipient_rejected(briefs_and_db) -> None:
    with pytest.raises(ValueError, match="Invalid recipient"):
        core.send("alice", "monty", "info", "hi", "")


def test_send_broadcast_fans_out(briefs_and_db) -> None:
    """Broadcast becomes one independent message per agent (sender excluded)."""
    sent = core.send("alice", "all", "info", "ping", "")
    assert sent["status"] == "sent"
    assert sent["to"] == "all"
    # Two agents in the fixture (alice, bob); alice excluded → 1 target.
    assert sent["broadcast_to"] == ["bob"]
    assert len(sent["ids"]) == 1


def test_invalid_priority_rejected(briefs_and_db) -> None:
    with pytest.raises(ValueError, match="Invalid priority"):
        core.send("alice", "bob", "emergency", "", "")


def test_mark_reserved_status_rejected(briefs_and_db) -> None:
    sent = core.send("alice", "bob", "info", "", "")
    with pytest.raises(ValueError, match="reserved for the human reviewer"):
        core.mark(sent["id"], "approved")


def test_mark_done(briefs_and_db) -> None:
    sent = core.send("alice", "bob", "info", "", "")
    marked = core.mark(sent["id"], "done")
    assert marked["new_status"] == "done"


def test_read_returns_full_message(briefs_and_db) -> None:
    sent = core.send("alice", "bob", "info", "subj", "body text")
    msg = core.read(sent["id"])
    assert msg["body"] == "body text"
    assert msg["subject"] == "subj"


def test_read_missing_returns_error(briefs_and_db) -> None:
    msg = core.read("00000000-0000-0000-0000-000000000000")
    assert "error" in msg


def test_search_subject_substring(briefs_and_db) -> None:
    core.send("alice", "bob", "info", "release v1", "")
    core.send("alice", "bob", "info", "lunch?", "")
    result = core.search(subject="release")
    assert result["count"] == 1
    assert result["messages"][0]["subject"] == "release v1"


def test_no_briefs_means_no_valid_senders(tmp_path: Path, monkeypatch) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(empty))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    with pytest.raises(ValueError, match="no briefs found"):
        core.send("alice", "bob", "info", "", "")

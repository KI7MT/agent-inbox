"""Broadcast (recipient='all') fan-out semantics.

A broadcast becomes one independent message per registered agent
(excluding the sender). Each recipient owns their own row, status, and
approval state — no shared global state.
"""

from pathlib import Path

import pytest

from agent_inbox import core


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    for name in ("alice", "bob", "carol", "dave"):
        (briefs_dir / f"{name}.md").write_text(f"# {name.title()}")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_broadcast_fan_out_excludes_sender(setup) -> None:
    sent = core.send("alice", "all", "info", "ping", "")
    assert sent["broadcast_to"] == ["bob", "carol", "dave"]
    assert len(sent["ids"]) == 3


def test_each_recipient_sees_their_own_copy(setup) -> None:
    core.send("alice", "all", "info", "morning", "stand-up in 5")
    for r in ("bob", "carol", "dave"):
        result = core.check(r)
        assert result["unread_count"] == 1, f"{r} missed the broadcast"
        assert result["messages"][0]["subject"] == "morning"


def test_one_recipient_marking_does_not_affect_others(setup) -> None:
    """The original bug: one row, one global status, mark-read by one
    recipient hid it from everyone else."""
    sent = core.send("alice", "all", "info", "ping", "")
    bob_msg = sent["ids"][0]
    core.mark(bob_msg, "read")
    # Carol and dave still see their copies.
    assert core.check("carol")["unread_count"] == 1
    assert core.check("dave")["unread_count"] == 1


def test_broadcast_with_no_other_agents_returns_no_recipients(
    tmp_path: Path, monkeypatch
) -> None:
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))

    sent = core.send("alice", "all", "info", "lonely broadcast", "")
    assert sent["status"] == "no_recipients"
    assert sent["ids"] == []
    assert sent["broadcast_to"] == []


def test_broadcast_action_each_needs_separate_approval(setup) -> None:
    """An urgent broadcast generates N pending approvals — one per recipient."""
    core.send("alice", "all", "urgent", "ship now", "")
    pending = core.list_pending_approval()
    assert pending["count"] == 3
    # Each row's recipient is one of the targets, not 'all'.
    recipients = {m["recipient"] for m in pending["messages"]}
    assert recipients == {"bob", "carol", "dave"}


def test_broadcast_mark_done_only_affects_one_recipient(setup) -> None:
    sent = core.send("alice", "all", "info", "fyi", "")
    bob_id = sent["ids"][0]
    core.mark(bob_id, "done")
    # Bob's copy is done; carol/dave still have their unread copies.
    bob_msg = core.read(bob_id)
    assert bob_msg["status"] == "done"
    assert core.check("carol")["unread_count"] == 1
    assert core.check("dave")["unread_count"] == 1

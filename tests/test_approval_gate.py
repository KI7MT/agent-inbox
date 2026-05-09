"""Approval gate enforcement.

`info` messages are act-on-immediately — they appear in inbox_check while
status='unread'. `action` and `urgent` are gated — they only become
visible to the recipient after the operator flips status to `approved`.
Until then they live in the operator's pending queue alone.
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
    (briefs_dir / "carol.md").write_text("# Carol")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_info_messages_visible_while_unread(setup) -> None:
    core.send("alice", "bob", "info", "fyi", "")
    result = core.check("bob")
    assert result["unread_count"] == 1
    assert result["messages"][0]["subject"] == "fyi"


def test_action_unread_hidden_from_recipient(setup) -> None:
    core.send("alice", "bob", "action", "deploy", "go staging")
    result = core.check("bob")
    assert result["unread_count"] == 0
    assert result["approved_count"] == 0
    assert result["messages"] == []


def test_urgent_unread_hidden_from_recipient(setup) -> None:
    core.send("alice", "bob", "urgent", "rollback", "")
    result = core.check("bob")
    assert result["messages"] == []


def test_action_visible_after_operator_approves(setup) -> None:
    sent = core.send("alice", "bob", "action", "deploy", "")
    # Bob can't see it.
    assert core.check("bob")["messages"] == []
    # Operator approves.
    core.operator_set_status(sent["id"], "approved")
    # Now bob sees it.
    result = core.check("bob")
    assert result["approved_count"] == 1
    assert result["messages"][0]["subject"] == "deploy"


def test_pending_queue_holds_unapproved_action(setup) -> None:
    """The operator's pending queue is the inverse view: it sees them."""
    core.send("alice", "bob", "action", "deploy", "")
    pending = core.list_pending_approval()
    assert pending["count"] == 1
    assert pending["messages"][0]["subject"] == "deploy"


def test_auto_approve_bypasses_gate(setup, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_INBOX_AUTO_APPROVE", "1")
    core.send("alice", "bob", "action", "auto", "")
    result = core.check("bob")
    assert result["approved_count"] == 1
    assert result["unread_count"] == 0


def test_rejected_action_stays_hidden(setup) -> None:
    sent = core.send("alice", "bob", "action", "rejected-thing", "")
    core.operator_set_status(sent["id"], "rejected")
    assert core.check("bob")["messages"] == []

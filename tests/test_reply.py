"""Tests for inbox_reply."""

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


def test_reply_routes_to_original_sender(setup) -> None:
    sent = core.send("alice", "bob", "info", "question", "what's up?")
    reply = core.reply("bob", sent["id"], "all good")
    assert reply["from"] == "bob"
    assert reply["to"] == "alice"
    assert reply["parent_id"] == sent["id"]


def test_reply_subject_gets_re_prefix(setup) -> None:
    sent = core.send("alice", "bob", "info", "question", "")
    reply = core.reply("bob", sent["id"], "answer")
    assert reply["subject"] == "Re: question"


def test_reply_subject_not_double_prefixed(setup) -> None:
    sent = core.send("alice", "bob", "info", "Re: thread", "")
    reply = core.reply("bob", sent["id"], "")
    assert reply["subject"] == "Re: thread"


def test_reply_to_broadcast_routes_to_original_sender(setup) -> None:
    """Broadcasts fan out at send time (one row per recipient). A reply
    goes back to the broadcast sender, regardless of which recipient's
    copy is being replied to."""
    sent = core.send("alice", "all", "info", "ping", "")
    # 3 agents in the fixture (alice/bob/carol); alice excluded → bob, carol
    assert sent["broadcast_to"] == ["bob", "carol"]
    bob_copy, carol_copy = sent["ids"]
    reply = core.reply("bob", bob_copy, "pong")
    assert reply["to"] == "alice"
    reply2 = core.reply("carol", carol_copy, "also pong")
    assert reply2["to"] == "alice"


def test_reply_from_non_recipient_rejected(setup) -> None:
    sent = core.send("alice", "bob", "info", "private", "")
    with pytest.raises(ValueError, match="Cannot reply"):
        core.reply("carol", sent["id"], "intercepted")


def test_reply_to_missing_parent(setup) -> None:
    result = core.reply("bob", "00000000-0000-0000-0000-000000000000", "hello")
    assert "error" in result


def test_reply_chains_via_parent_id(setup) -> None:
    a = core.send("alice", "bob", "info", "topic", "")
    b = core.reply("bob", a["id"], "reply 1")
    c = core.reply("alice", b["id"], "reply to reply")
    assert c["parent_id"] == b["id"]
    msg_b = core.read(b["id"])
    assert msg_b["parent_id"] == a["id"]


def test_reply_priority_can_escalate(setup) -> None:
    sent = core.send("alice", "bob", "info", "question", "")
    reply = core.reply("bob", sent["id"], "this is urgent", priority="urgent")
    assert reply["priority"] == "urgent"

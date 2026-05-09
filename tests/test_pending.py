"""Tests for the operator's approval queue."""

from pathlib import Path

import pytest

from agent_inbox import cli, core


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_pending_excludes_info(setup) -> None:
    core.send("alice", "bob", "info", "info-msg", "")
    core.send("alice", "bob", "action", "action-msg", "")
    core.send("alice", "bob", "urgent", "urgent-msg", "")
    result = core.list_pending_approval()
    assert result["count"] == 2
    subjects = {m["subject"] for m in result["messages"]}
    assert subjects == {"action-msg", "urgent-msg"}


def test_pending_orders_urgent_first(setup) -> None:
    core.send("alice", "bob", "action", "second", "")
    core.send("alice", "bob", "urgent", "first", "")
    result = core.list_pending_approval()
    subjects = [m["subject"] for m in result["messages"]]
    assert subjects == ["first", "second"]


def test_pending_excludes_already_acted_on(setup) -> None:
    sent = core.send("alice", "bob", "action", "done-already", "")
    core.operator_set_status(sent["id"], "approved")
    result = core.list_pending_approval()
    assert result["count"] == 0


def test_pending_excludes_auto_approved(setup, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_INBOX_AUTO_APPROVE", "1")
    core.send("alice", "bob", "action", "auto-approved", "")
    core.send("alice", "bob", "urgent", "auto-approved-too", "")
    result = core.list_pending_approval()
    assert result["count"] == 0


def test_cli_pending_subcommand(setup, capsys) -> None:
    core.send("alice", "bob", "action", "needs-review", "details")
    rc = cli.main(["pending"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "needs-review" in out
    assert "action" in out


def test_cli_pending_when_empty(setup, capsys) -> None:
    rc = cli.main(["pending"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "no messages awaiting approval" in out


def test_cli_reply_subcommand(setup, capsys) -> None:
    sent = core.send("alice", "bob", "info", "question", "")
    rc = cli.main(["reply", "--from", "bob", sent["id"], "answer"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "bob -> alice" in out

"""End-to-end tests for the operator CLI via build_parser + dispatch."""

from pathlib import Path

import pytest

from agent_inbox import cli, core


@pytest.fixture
def briefs_and_db(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "operator.md").write_text("# Operator")
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_cli_send_then_list(briefs_and_db, capsys) -> None:
    rc = cli.main(["send", "--from", "operator", "--to", "alice", "review", "please look at PR 42"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "operator -> alice" in out

    rc = cli.main(["list", "--for", "alice"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "review" in out
    assert "alice" in out


def test_cli_approve_flips_status(briefs_and_db, capsys) -> None:
    sent = core.send("operator", "alice", "action", "deploy", "to staging")
    rc = cli.main(["approve", sent["id"]])
    assert rc == 0
    msg = core.read(sent["id"])
    assert msg["status"] == "approved"


def test_cli_reject_flips_status(briefs_and_db, capsys) -> None:
    sent = core.send("operator", "alice", "urgent", "ship now", "")
    rc = cli.main(["reject", sent["id"]])
    assert rc == 0
    msg = core.read(sent["id"])
    assert msg["status"] == "rejected"


def test_cli_agents_lists_briefs(briefs_and_db, capsys) -> None:
    rc = cli.main(["agents"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "operator" in out
    assert "alice" in out


def test_cli_brief_prints_content(briefs_and_db, capsys) -> None:
    rc = cli.main(["brief", "alice"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Alice" in out


def test_cli_paths_prints_paths(briefs_and_db, capsys) -> None:
    rc = cli.main(["paths"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "briefs_dir:" in out
    assert "db_path:" in out


def test_cli_send_default_sender_is_operator(briefs_and_db, capsys) -> None:
    rc = cli.main(["send", "--to", "alice", "subj", "body"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "operator -> alice" in out

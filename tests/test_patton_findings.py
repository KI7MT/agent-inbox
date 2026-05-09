"""Regression tests for Patton's failure-analysis findings on v0.3.2.

These pin the v0.3.3 fixes so future refactors don't reopen the holes:

  1. inbox_search with a too-long subject pattern raises a clean ValueError
     instead of a raw sqlite3.OperationalError ("LIKE or GLOB pattern too
     complex").
  2. inbox_reply re-validates the subject AFTER the "Re: " prefix is added
     so a parent at MAX_SUBJECT_LEN can't produce a 4-char-over reply.
  3. inbox_reply hard-errors when the original sender's brief has been
     removed since the parent was sent (otherwise the reply lands in a row
     the registry can't reach).
  4. The operator name is implicitly registered (matches Go), so the CLI
     and MCP server work on a fresh install without an operator.md brief.
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


# --- Finding 1: search subject length cap ---------------------------------


def test_search_subject_at_cap_works(setup) -> None:
    result = core.search(subject="x" * core.MAX_SEARCH_SUBJECT_LEN)
    assert result["count"] == 0


def test_search_subject_over_cap_clean_error(setup) -> None:
    with pytest.raises(ValueError, match="Search subject too long"):
        core.search(subject="x" * (core.MAX_SEARCH_SUBJECT_LEN + 1))


def test_search_50k_subject_does_not_leak_operational_error(setup) -> None:
    """Patton's exact reproducer — 50k chars used to crash with
    sqlite3.OperationalError. Now it's a ValueError."""
    with pytest.raises(ValueError, match="Search subject too long"):
        core.search(subject="x" * 50_000)


# --- Finding 2: reply subject cap after Re: prefix ------------------------


def test_reply_subject_capped_after_prefix(setup) -> None:
    """Parent subject at MAX_SUBJECT_LEN — reply would prefix "Re: " and
    overflow by 4. Should be rejected."""
    sent = core.send("alice", "bob", "info", "x" * core.MAX_SUBJECT_LEN, "")
    with pytest.raises(ValueError, match="Subject too long"):
        core.reply("bob", sent["id"], "")


def test_reply_subject_just_under_cap_works(setup) -> None:
    """Parent subject 4 under the cap — reply produces "Re: " + 496 = 500
    exactly, should succeed."""
    sent = core.send("alice", "bob", "info", "x" * (core.MAX_SUBJECT_LEN - 4), "")
    reply = core.reply("bob", sent["id"], "")
    assert len(reply["subject"]) == core.MAX_SUBJECT_LEN


def test_reply_to_already_prefixed_subject_does_not_re_prefix(setup) -> None:
    """If the parent subject already starts with "Re:", the reply doesn't
    prefix again — so a maxed-out reply chain doesn't keep growing the
    subject by 4 chars on every hop."""
    parent_subject = "Re: " + "x" * (core.MAX_SUBJECT_LEN - 4)
    sent = core.send("alice", "bob", "info", parent_subject, "")
    reply = core.reply("bob", sent["id"], "")
    assert reply["subject"] == parent_subject
    assert len(reply["subject"]) == core.MAX_SUBJECT_LEN


# --- Finding 3: orphan recipient validation -------------------------------


def test_reply_to_orphan_sender_rejected(setup) -> None:
    """Original sender's brief removed after the parent was sent — reply
    must hard-error rather than create an invisible row."""
    sent = core.send("alice", "bob", "info", "topic", "")
    (setup / "alice.md").unlink()
    with pytest.raises(ValueError, match="no longer in the brief registry"):
        core.reply("bob", sent["id"], "answer")


def test_reply_to_operator_orphan_still_works(setup) -> None:
    """The operator is implicitly registered even without a brief, so a
    reply destined for the operator never orphans."""
    sent = core.send("operator", "bob", "info", "topic", "")
    # No operator.md to remove — operator is already implicit.
    reply = core.reply("bob", sent["id"], "answer")
    assert reply["to"] == "operator"


# --- Operator implicit-allow (alignment with Go) --------------------------


def test_operator_can_send_without_operator_brief(tmp_path: Path, monkeypatch) -> None:
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))

    sent = core.send("operator", "alice", "info", "fyi", "")
    assert sent["status"] == "sent"


def test_operator_can_receive_without_operator_brief(tmp_path: Path, monkeypatch) -> None:
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))

    sent = core.send("alice", "operator", "info", "fyi", "")
    assert sent["status"] == "sent"
    pending = core.check("operator")
    assert pending["unread_count"] == 1


def test_custom_operator_name_implicit_allow(tmp_path: Path, monkeypatch) -> None:
    """AGENT_INBOX_OPERATOR=ki7mt should let "ki7mt" pass without a brief."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "ki7mt")

    sent = core.send("ki7mt", "alice", "info", "from custom operator", "")
    assert sent["status"] == "sent"

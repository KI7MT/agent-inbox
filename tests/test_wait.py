"""Tests for the long-poll inbox_wait operation."""

import threading
import time
from pathlib import Path

import pytest

from agent_inbox import core


@pytest.fixture
def briefs_and_db(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_wait_returns_immediately_when_mail_pending(briefs_and_db) -> None:
    core.send("alice", "bob", "info", "hi", "")
    started = time.monotonic()
    result = core.wait("bob", timeout_seconds=10)
    elapsed = time.monotonic() - started
    assert result["timed_out"] is False
    assert result["unread_count"] == 1
    assert elapsed < 1.0


def test_wait_times_out_when_no_mail(briefs_and_db) -> None:
    started = time.monotonic()
    result = core.wait("bob", timeout_seconds=2)
    elapsed = time.monotonic() - started
    assert result["timed_out"] is True
    assert result["messages"] == []
    assert 1.5 <= elapsed <= 4.0


def test_wait_wakes_on_new_message(briefs_and_db) -> None:
    def deliver_after_delay() -> None:
        time.sleep(1.5)
        core.send("alice", "bob", "info", "ping", "")

    t = threading.Thread(target=deliver_after_delay, daemon=True)
    started = time.monotonic()
    t.start()
    result = core.wait("bob", timeout_seconds=10)
    elapsed = time.monotonic() - started
    t.join(timeout=5)
    assert result["timed_out"] is False
    assert result["unread_count"] == 1
    assert 1.0 <= elapsed <= 4.0


def test_wait_unknown_recipient_rejected(briefs_and_db) -> None:
    with pytest.raises(ValueError, match="Invalid recipient"):
        core.wait("ghost", timeout_seconds=1)

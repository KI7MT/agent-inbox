from pathlib import Path

import pytest

from agent_inbox import core


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice\n\nReviews PRs.\n")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


def test_brief_returns_content(setup) -> None:
    result = core.brief("alice")
    assert "Reviews PRs" in result["brief"]
    assert result["agent"] == "alice"


def test_brief_unknown_agent_rejected(setup) -> None:
    with pytest.raises(ValueError, match="Invalid agent"):
        core.brief("ghost")

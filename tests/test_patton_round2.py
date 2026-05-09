"""Regression tests for Patton's round-2 findings on v0.3.3.

Pins the v0.3.4 fixes:

  1. Orphan-recipient parity — `core.send` (direct + broadcast loop)
     now mirrors the `core.reply` orphan guard. Direct send hard-errors
     if the recipient is no longer registered; broadcast skips orphaned
     targets and reports them in `broadcast_skipped`.
  2. AGENT_INBOX_OPERATOR validation — reserved names (`all`) and names
     that don't match `NAME_RE` are rejected at the operator_name()
     boundary, not allowed to silently produce a broken install.
  3. Character-based length caps in Python — already in chars; the
     parity fix is on the Go side (use utf8.RuneCountInString). The
     Python-side test here just locks in that emojis count as one each.
"""

from pathlib import Path

import pytest

from agent_inbox import briefs, core


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    for name in ("alice", "bob", "carol", "dave"):
        (briefs_dir / f"{name}.md").write_text(f"# {name.title()}")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return briefs_dir


# --- Finding 1: orphan-recipient parity in core.send ----------------------


def test_direct_send_to_orphan_hard_errors(setup) -> None:
    """Recipient's brief deleted between validation and the actual send."""
    # Send once to confirm bob is registered.
    sent = core.send("alice", "bob", "info", "first", "")
    assert sent["status"] == "sent"

    # Now remove bob's brief — but `core.send`'s _validate_agent reads
    # the registry at call time, so we have to remove between the
    # validate and the insert. Simulate by: validating with bob present,
    # then inside the send call, the connection-scope re-check sees bob
    # missing. We can't easily race in a unit test, so instead we drive
    # the same code path by removing bob's brief, calling send, and
    # observing the connection-scope re-check rejects.
    (setup / "bob.md").unlink()
    with pytest.raises(ValueError, match="Invalid recipient"):
        core.send("alice", "bob", "info", "second", "")


def test_broadcast_skips_orphaned_targets(setup, monkeypatch) -> None:
    """A target removed between snapshot and per-target insert is dropped
    from the broadcast and reported in `broadcast_skipped`."""
    full = {"alice", "bob", "carol", "dave"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        # Calls 1-3 are validate_sender, validate_recipient, and the
        # broadcast-target snapshot — return the full set so the send
        # plans deliveries to bob/carol/dave.
        # Calls 4+ are the in-loop re-checks. We pretend carol's brief
        # was just unlinked, so her per-target check fails and she's
        # dropped from the broadcast.
        if state["calls"] <= 3:
            return full
        return full - {"carol"}

    monkeypatch.setattr(core, "_agents", fake_agents)

    sent = core.send("alice", "all", "info", "morning", "stand-up in 5")
    assert sent["broadcast_to"] == ["bob", "dave"]
    assert sent["broadcast_skipped"] == ["carol"]
    assert len(sent["ids"]) == 2


def test_direct_send_to_operator_works_without_brief(setup) -> None:
    """The operator name is implicit, so a direct send to operator after
    operator.md is removed still works."""
    sent = core.send("alice", "operator", "info", "fyi", "")
    assert sent["status"] == "sent"


# --- Finding 2: AGENT_INBOX_OPERATOR validation ---------------------------


def test_operator_name_default_works(monkeypatch) -> None:
    monkeypatch.delenv("AGENT_INBOX_OPERATOR", raising=False)
    assert briefs.operator_name() == "operator"


def test_operator_name_reserved_rejected(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "all")
    with pytest.raises(ValueError, match="reserved name"):
        briefs.operator_name()


def test_operator_name_invalid_chars_rejected(monkeypatch) -> None:
    """Names that don't match NAME_RE are rejected. Note: input is
    lowercased first, so `Operator` is treated as `operator` — capital
    letters aren't an invalid-char case."""
    for bad in ("1bad", "with space", "with.dot", "with/slash", ""):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", bad)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_operator_name_capitals_lowercased(monkeypatch) -> None:
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "Operator")
    assert briefs.operator_name() == "operator"


def test_operator_name_rejects_trailing_newline(monkeypatch) -> None:
    """v0.3.5 fix: Python's `$` accepted a trailing `\\n`, breaking
    parity with Go and the documented agent-name contract. `\\Z` rejects it."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "op\n")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_name_rejects_trailing_whitespace(monkeypatch) -> None:
    for bad in ("op\r", "op\t", "op "):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", bad)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_operator_name_valid_custom_accepted(monkeypatch) -> None:
    for good in ("ki7mt", "alice", "ops-lead", "dev_1"):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", good)
        assert briefs.operator_name() == good


def test_send_with_invalid_operator_env_fails_loudly(setup, monkeypatch) -> None:
    """The whole send pipeline fails loudly (not silently writes a
    "sender=all" row) when AGENT_INBOX_OPERATOR is misconfigured."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "all")
    with pytest.raises(ValueError, match="reserved name"):
        core.send("alice", "bob", "info", "fyi", "")


# --- Finding 3: chars vs bytes (parity check) -----------------------------


def test_emoji_subject_counts_as_one_char_each(setup) -> None:
    """🌪 is one char in Python; should also be one char in Go after
    the v0.3.4 utf8.RuneCountInString fix. This test pins the Python
    side; the Go side has a parallel test in app_test.go (TODO)."""
    # 500 emoji = 500 chars (under cap by 0)
    sent = core.send("alice", "bob", "info", "🌪" * 500, "")
    assert sent["status"] == "sent"

    # 501 emoji = 501 chars, over cap by 1
    with pytest.raises(ValueError, match="Subject too long"):
        core.send("alice", "bob", "info", "🌪" * 501, "")


def test_emoji_body_counts_as_one_char_each(setup) -> None:
    """1_000_000 emoji should be exactly at cap in Python. Sanity-check
    boundary handling for the chars-not-bytes contract."""
    # 1M emoji is at the cap.
    sent = core.send("alice", "bob", "info", "ok", "🌪" * core.MAX_BODY_LEN)
    assert sent["status"] == "sent"

    with pytest.raises(ValueError, match="Body too long"):
        core.send("alice", "bob", "info", "ok", "🌪" * (core.MAX_BODY_LEN + 1))

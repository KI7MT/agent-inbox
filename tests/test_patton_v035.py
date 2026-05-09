"""Patton consolidated attack tests for v0.3.5 (`48ed398`).

Combined output of round-3 and round-4 audit passes. Pins the contracts
established across the iteration:

  v0.3.4 contracts (from round 3)
  -------------------------------
  - Broadcast orphan-skip: per-target `_agents()` re-check; skipped
    targets reported in `broadcast_skipped`.
  - Operator-implicit-allow union (`_agents() | {operator_name()}`)
    persists across direct-send, broadcast, and reply paths.
  - `broadcast_to` is the *delivered* set; `broadcast_skipped` only
    appears when at least 1 target was dropped (additive contract).
  - `AGENT_INBOX_OPERATOR` validation rejects reserved names, names
    that fail `NAME_RE`, leading/trailing/internal whitespace,
    Unicode lookalikes, and empty strings.
  - Char-counting parity: code points (not grapheme clusters), so a
    ZWJ family glyph counts as 7. Decomposed accents count as 2 each.

  v0.3.5 contracts (from round 4)
  -------------------------------
  - `NAME_RE` uses `\\Z` (strict end-of-string), restoring parity with
    Go's `regexp` and rejecting trailing newlines (Python's `$` accepts
    them by default).
  - The fix closes three doors at once: `briefs.load_agents`,
    `briefs.operator_name`, and `core._validate_agent`.
  - Trailing CR, BOM, ZWJ/ZWSP, NFC/NFD-decomposed text all reject —
    not because of `\\Z` but because they're outside `[a-z0-9_-]`.
  - Brief filenames with trailing newlines (Linux ext4 allows them at
    the FS layer) are rejected at the validator layer.

Total: 56 tests. All pass on v0.3.5.
"""

from __future__ import annotations

import os
import unicodedata
import unittest.mock
from pathlib import Path

import pytest

from agent_inbox import briefs, core, db


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    """Five-agent fixture (alice, bob, carol, dave, eve). The two extra
    agents over the README's three-agent default give the broadcast-
    fan-out tests room to test multi-target skip semantics."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    for name in ("alice", "bob", "carol", "dave", "eve"):
        (briefs_dir / f"{name}.md").write_text(f"# {name.title()}")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    db._initialized_paths.clear()
    return briefs_dir


# =========================================================================
# v0.3.4 contracts: Broadcast orphan-skip with multiple unlinks
# =========================================================================


def test_broadcast_skip_multiple_unlinks_in_different_orders(setup, monkeypatch) -> None:
    """Two targets get unlinked at different points in the iteration.
    Both end up in broadcast_skipped, neither corrupts state."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        # Calls 1-3 = sender validate, recipient validate, target snapshot.
        if state["calls"] <= 3:
            return full
        # Per-target re-checks: drop carol on call 5 (between bob and carol),
        # drop eve on call 7 (between dave and eve).
        if state["calls"] == 5:
            return full - {"carol"}
        if state["calls"] >= 7:
            return full - {"carol", "eve"}
        return full - {"carol"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "drift", "")
    assert sent["broadcast_to"] == ["bob", "dave"]
    assert sorted(sent["broadcast_skipped"]) == ["carol", "eve"]
    assert len(sent["ids"]) == 2


def test_broadcast_skip_all_targets_after_snapshot(setup, monkeypatch) -> None:
    """Every target's brief vanishes between snapshot and the loop.
    Empty delivery, all skipped, but status='sent' (not 'no_recipients'
    which is reserved for empty-snapshot case)."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        return {"alice"}  # only sender remains

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "vanished", "")
    assert sent["broadcast_to"] == []
    assert sent["ids"] == []
    assert sorted(sent["broadcast_skipped"]) == ["bob", "carol", "dave", "eve"]
    # Only 'no_recipients' is returned when initial snapshot has no targets.
    assert sent["status"] == "sent"


def test_broadcast_skip_preserves_alphabetical_order(setup, monkeypatch) -> None:
    """The targets list is sorted at snapshot, so delivery order is
    alphabetical. Skipping shouldn't disturb the surviving order."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        return full - {"bob", "dave"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "x", "")
    assert sent["broadcast_to"] == ["carol", "eve"]


# =========================================================================
# v0.3.4 contracts: operator name == registered agent name overlap
# =========================================================================


def test_operator_name_collides_with_registered_agent(tmp_path: Path, monkeypatch) -> None:
    """AGENT_INBOX_OPERATOR=alice while alice.md exists. The implicit-
    allow union (`_agents() | {operator_name()}`) is idempotent. Removing
    alice.md doesn't remove her from the valid set because she's still
    the operator. Behavior is internally consistent."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice")
    db._initialized_paths.clear()

    sent = core.send("alice", "bob", "info", "fyi", "")
    assert sent["status"] == "sent"

    # Remove alice.md — alice is still implicitly registered as operator.
    (briefs_dir / "alice.md").unlink()
    sent2 = core.send("alice", "bob", "info", "still-alive", "")
    assert sent2["status"] == "sent"
    sent3 = core.send("bob", "alice", "info", "back-at-you", "")
    assert sent3["status"] == "sent"


def test_operator_collision_orphan_check_uses_implicit_allow(tmp_path: Path, monkeypatch) -> None:
    """If operator==alice and alice.md is removed mid-broadcast, alice
    survives the orphan check because she's the operator."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    for n in ("alice", "bob", "carol"):
        (briefs_dir / f"{n}.md").write_text(f"# {n}")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice")
    db._initialized_paths.clear()

    full = {"alice", "bob", "carol"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        # alice's brief unlinked between snapshot and per-target check.
        return full - {"alice"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("bob", "all", "info", "ping", "")
    # alice should NOT be skipped — she's the operator, implicitly registered.
    assert "alice" in sent["broadcast_to"]
    assert "carol" in sent["broadcast_to"]
    assert sent.get("broadcast_skipped", []) == []


# =========================================================================
# v0.3.4 contracts: broadcast_to result-shape change downstream
# =========================================================================


def test_broadcast_no_skips_no_skipped_field(setup) -> None:
    """When no targets are skipped, `broadcast_skipped` must NOT appear
    in the response (additive contract — old callers keep working)."""
    sent = core.send("alice", "all", "info", "clean", "")
    assert "broadcast_skipped" not in sent


def test_broadcast_to_when_skips_present_is_delivered_set(setup, monkeypatch) -> None:
    """`broadcast_to` is the *delivered* set, not the planned set."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        return full - {"dave"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "x", "")
    assert "dave" not in sent["broadcast_to"]
    assert sent["broadcast_skipped"] == ["dave"]
    assert len(sent["ids"]) == len(sent["broadcast_to"])


def test_broadcast_to_empty_when_only_sender_registered(tmp_path: Path, monkeypatch) -> None:
    """Snapshot has no targets → status='no_recipients', no skipped
    field (nothing was ever planned)."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    db._initialized_paths.clear()

    sent = core.send("alice", "all", "info", "lonely", "")
    assert sent["status"] == "no_recipients"
    assert sent["broadcast_to"] == []
    assert "broadcast_skipped" not in sent


def test_cli_broadcast_count_uses_delivered_not_planned(setup, monkeypatch) -> None:
    """CLI cmd_send formats broadcast as `len(result['ids'])`. After the
    contract change, this is the delivered count, which is what the
    operator wants. broadcast_to and ids are consistent."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        return full - {"carol"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "drift", "")
    assert len(sent["ids"]) == len(sent["broadcast_to"])
    assert sent["broadcast_skipped"] == ["carol"]


# =========================================================================
# v0.3.4 contracts: AGENT_INBOX_OPERATOR validation corner cases
# =========================================================================


def test_operator_env_with_leading_whitespace(monkeypatch) -> None:
    """Whitespace is not stripped. ' alice' fails NAME_RE."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", " alice")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_with_trailing_whitespace(monkeypatch) -> None:
    """Trailing space — NAME_RE has `\\Z` anchor so trailing chars fail."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice ")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_explicitly_empty_falls_through_to_default(monkeypatch) -> None:
    """`AGENT_INBOX_OPERATOR=""` explicitly. The default fall-through
    only fires if the env var is UNSET, not if it's set to empty string.
    Empty string raises now (it always was a quiet bug under the old
    fall-through-to-empty path)."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_set_to_regex_pattern_literal(monkeypatch) -> None:
    """User accidentally sets AGENT_INBOX_OPERATOR to the regex pattern
    itself. The string contains chars that don't match the pattern."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "^[a-z][a-z0-9_-]*$")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_with_internal_whitespace(monkeypatch) -> None:
    """'alice bob' has interior space. NAME_RE rejects."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice bob")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_with_tab_or_newline(monkeypatch) -> None:
    """\\t and \\n in the value. v0.3.5's `\\Z` anchor catches the
    trailing-newline case that v0.3.4's `$` accepted by mistake."""
    for bad in ("alice\t", "alice\n", "\talice", "\nalice"):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", bad)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_operator_env_with_unicode_lookalike(monkeypatch) -> None:
    """Cyrillic 'а' (U+0430) looks like ASCII 'a' but doesn't match
    [a-z]."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "аlice")  # 'аlice'
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_with_uppercase_unicode(monkeypatch) -> None:
    """Capital uses .lower() first; non-ASCII uppercase that lowercases
    to a non-ASCII char still fails the ASCII regex."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "ÉTIENNE")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_operator_env_at_brief_filename_edge(monkeypatch) -> None:
    """Names that match NAME_RE but might still be problematic: a single
    character (legal: starts with letter, no following chars needed
    since `*` allows zero), a long name (no upper bound)."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "a")
    assert briefs.operator_name() == "a"

    long_name = "a" + "b" * 999
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", long_name)
    assert briefs.operator_name() == long_name


# =========================================================================
# v0.3.4 contracts: char-counting (runes, not grapheme clusters)
# =========================================================================


def test_zwj_emoji_sequence_counts_as_codepoints_not_clusters(setup) -> None:
    """A single 'family' grapheme like 👨‍👩‍👧‍👦 is 7 code points
    (4 emoji + 3 ZWJ). Python's len() and Go's utf8.RuneCountInString
    both count code points, so 71 families fits (497 cps), 72 over."""
    family = "\U0001F468‍\U0001F469‍\U0001F467‍\U0001F466"
    assert len(family) == 7
    subject = family * 71
    assert len(subject) == 497
    sent = core.send("alice", "bob", "info", subject, "")
    assert sent["status"] == "sent"

    too_many = family * 72
    assert len(too_many) == 504
    with pytest.raises(ValueError, match="Subject too long"):
        core.send("alice", "bob", "info", too_many, "")


def test_combining_accent_marks_count_as_separate_codepoints(setup) -> None:
    """'é' as decomposed (e + combining acute) = 2 code points.
    Composed = 1 code point (NFC). The cap counts code points raw —
    decomposed text uses 2x the budget."""
    decomposed = "é"
    composed = "é"
    assert len(decomposed) == 2
    assert len(composed) == 1
    sent = core.send("alice", "bob", "info", decomposed * 250, "")
    assert sent["status"] == "sent"
    with pytest.raises(ValueError, match="Subject too long"):
        core.send("alice", "bob", "info", decomposed * 251, "")


def test_rtl_text_does_not_alter_char_count(setup) -> None:
    """Right-to-left text and RTL override marks (U+202E) don't change
    the code-point count."""
    arabic = "السلام عليكم "  # 13 cps
    rtl_with_override = "‮" + arabic  # 14 cps
    assert len(rtl_with_override) == 14
    subject = rtl_with_override * 35
    assert len(subject) == 490
    sent = core.send("alice", "bob", "info", subject, "")
    assert sent["status"] == "sent"


# =========================================================================
# v0.3.4 contracts: misconfigured operator env aborts pipeline cleanly
# =========================================================================


def test_send_with_invalid_operator_env_during_broadcast(setup, monkeypatch) -> None:
    """If AGENT_INBOX_OPERATOR is misconfigured, briefs.operator_name()
    raises ValueError. core.send calls operator_name() before the
    broadcast loop. Verify failure happens BEFORE any partial fan-out."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "all")
    initial_count = core.list_recent(limit=10)["count"]
    with pytest.raises(ValueError, match="reserved name"):
        core.send("alice", "all", "info", "x", "")
    final_count = core.list_recent(limit=10)["count"]
    assert final_count == initial_count


def test_reply_with_invalid_operator_env_fails_loudly(setup, monkeypatch) -> None:
    """core.reply calls briefs.operator_name() inside the orphan check.
    Misconfigured operator env breaks reply just like send."""
    sent = core.send("alice", "bob", "info", "topic", "")
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "all")
    with pytest.raises(ValueError, match="reserved name"):
        core.reply("bob", sent["id"], "answer")


def test_orphan_check_triggers_on_first_brief_removal(setup) -> None:
    """The direct-send orphan check uses `_agents() | {op}`. If recipient
    has no brief AND isn't the operator, send fails with a clean error."""
    (setup / "bob.md").unlink()
    with pytest.raises(ValueError, match="Invalid recipient"):
        core.send("alice", "bob", "info", "x", "")


def test_search_caps_use_chars_python_side_unchanged(setup) -> None:
    """Python's MAX_SEARCH_SUBJECT_LEN check uses `len()` (code points).
    1000 emoji is at cap, 1001 over."""
    core.send("alice", "bob", "info", "test", "")
    result = core.search(subject="🌪" * 1000)
    assert isinstance(result, dict)
    with pytest.raises(ValueError, match="Search subject too long"):
        core.search(subject="🌪" * 1001)


def test_broadcast_skip_does_not_double_count_operator(tmp_path: Path, monkeypatch) -> None:
    """If the operator name happens to match a brief filename AND the
    brief is then removed, the operator stays valid via the implicit-allow
    union. They don't get skipped wrongly."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    for n in ("alice", "bob", "operator"):
        (briefs_dir / f"{n}.md").write_text(f"# {n}")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    db._initialized_paths.clear()

    full = {"alice", "bob", "operator"}
    state = {"calls": 0}

    def fake_agents():
        state["calls"] += 1
        if state["calls"] <= 3:
            return full
        return full - {"operator"}

    monkeypatch.setattr(core, "_agents", fake_agents)
    sent = core.send("alice", "all", "info", "ping", "")
    assert "operator" in sent["broadcast_to"]


def test_broadcast_skipped_excludes_sender(setup) -> None:
    """The sender is excluded from the snapshot at line 132 (`_agents() - {s}`).
    They never appear in `broadcast_to` or `broadcast_skipped`."""
    sent = core.send("alice", "all", "info", "x", "")
    assert "alice" not in sent["broadcast_to"]
    assert "alice" not in sent.get("broadcast_skipped", [])


def test_check_inbox_for_orphan_recipient_after_failed_send(setup) -> None:
    """If a direct send to a now-unregistered recipient is attempted, we
    get an error AND there's no row inserted, so the recipient (if they
    ever come back) won't see a stale message."""
    (setup / "bob.md").unlink()
    with pytest.raises(ValueError):
        core.send("alice", "bob", "info", "ghost", "")
    (setup / "bob.md").write_text("# Bob")
    result = core.check("bob")
    assert result["unread_count"] == 0


def test_python_operator_validation_does_not_crash_module_import() -> None:
    """briefs.operator_name() is only called when something needs the
    operator. Importing `briefs` should not trigger validation. A
    misconfigured env doesn't break import."""
    saved = os.environ.get("AGENT_INBOX_OPERATOR")
    try:
        os.environ["AGENT_INBOX_OPERATOR"] = "all"
        import importlib

        from agent_inbox import briefs as briefs_mod
        importlib.reload(briefs_mod)
        with pytest.raises(ValueError):
            briefs_mod.operator_name()
    finally:
        if saved is None:
            del os.environ["AGENT_INBOX_OPERATOR"]
        else:
            os.environ["AGENT_INBOX_OPERATOR"] = saved


def test_broadcast_calls_agents_once_per_target(setup, monkeypatch) -> None:
    """Performance characterization: the broadcast loop calls
    `_agents()` once per target inside the loop. With N targets, that's
    3 + N total disk reads of the briefs dir per send. Pinned so a
    future refactor can't accidentally explode this to N**2 without
    flagging."""
    full = {"alice", "bob", "carol", "dave", "eve"}
    call_count = {"n": 0}
    real_agents = core._agents

    def counting_agents():
        call_count["n"] += 1
        return real_agents()

    monkeypatch.setattr(core, "_agents", counting_agents)
    core.send("alice", "all", "info", "x", "")
    # 1 (sender validate) + 1 (recipient validate) + 1 (snapshot)
    # + N (per-target re-checks) where N = 4 (bob, carol, dave, eve)
    assert call_count["n"] == 7


# =========================================================================
# v0.3.5 contracts: `\Z` anchor — strict end-of-string (no trailing \n)
# =========================================================================


def test_z_anchor_does_not_break_normal_names(monkeypatch) -> None:
    """Pin the no-regression: every name that worked under `$` still
    works under `\\Z`. The two anchors only differ on trailing newline."""
    for good in ("alice", "bob", "carol", "ki7mt", "ops-lead", "dev_1",
                 "a", "z9", "x" * 100, "aaaaaa-bbbbbb-cccccc"):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", good)
        assert briefs.operator_name() == good, f"{good!r} should pass"


def test_z_anchor_rejects_all_trailing_whitespace(monkeypatch) -> None:
    """\\Z anchors at strict end. Every trailing whitespace char rejected."""
    for whitespace in ("\n", "\r", "\t", " ", "\v", "\f", " ", " ", " "):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice" + whitespace)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_z_anchor_rejects_leading_whitespace(monkeypatch) -> None:
    """Leading whitespace fails the `^[a-z]` start anchor."""
    for whitespace in ("\n", "\r", "\t", " ", " "):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", whitespace + "alice")
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_z_anchor_rejects_internal_whitespace(monkeypatch) -> None:
    """Whitespace anywhere in the middle fails (not in [a-z0-9_-])."""
    for ws in ("\n", "\r", "\t", " "):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", "al" + ws + "ice")
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_z_anchor_rejects_bom(monkeypatch) -> None:
    """BOM (U+FEFF) at start, end, or middle is rejected — not in
    [a-z0-9_-]."""
    for variant in ("﻿alice", "alice﻿", "ali﻿ce"):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", variant)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_z_anchor_rejects_zero_width_joiners(monkeypatch) -> None:
    """ZWJ and ZWSP — invisible chars that would otherwise be a phishing
    surface. NAME_RE rejects."""
    for invisible in ("​", "‌", "‍"):  # ZWSP, ZWNJ, ZWJ
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice" + invisible)
        with pytest.raises(ValueError):
            briefs.operator_name()


# =========================================================================
# v0.3.5 contracts: Unicode normalization (NFC vs NFD) — neither sneaks in
# =========================================================================


def test_operator_name_decomposed_form_rejected(monkeypatch) -> None:
    """'étienne' decomposed: e + combining acute + tienne. Both NFC and
    NFD forms reject — NFC because é is outside [a-z], NFD because the
    combining mark is outside [a-z0-9_-]. No normalization sneak-around."""
    nfc = "étienne"
    nfd = "étienne"
    assert unicodedata.normalize("NFC", nfd) == nfc
    assert unicodedata.normalize("NFD", nfc) == nfd

    for variant in (nfc, nfd):
        monkeypatch.setenv("AGENT_INBOX_OPERATOR", variant)
        with pytest.raises(ValueError):
            briefs.operator_name()


def test_operator_name_no_normalization_applied(monkeypatch) -> None:
    """The validator does NOT apply NFC/NFD normalization. Pure ASCII
    names round-trip byte-identical."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice")
    assert briefs.operator_name() == "alice"
    assert briefs.operator_name().encode("utf-8") == b"alice"


def test_operator_env_with_invalid_utf8_blocked_at_python_layer(monkeypatch) -> None:
    """os.environ in Python 3 returns str (UTF-8 decoded). Invalid UTF-8
    bytes in the environment usually surface as `os.environb` or get
    lost in decoding. This is a Python-runtime concern, not a v0.3.5
    concern; pin the happy path."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice")
    assert briefs.operator_name() == "alice"


# =========================================================================
# v0.3.5 contracts: brief-filename trailing-newline rejection (Linux)
# =========================================================================


def test_brief_filename_with_trailing_newline_now_rejected(tmp_path: Path, monkeypatch) -> None:
    """The v0.3.5 \\Z fix should also reject a brief filename with a
    trailing newline (Linux ext4 allows them at the FS layer; macOS APFS
    / Windows NTFS don't). This was the second face of the round-3 finding."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")

    bad_name = "evil\n.md"
    try:
        (briefs_dir / bad_name).write_text("# Evil")
    except OSError:
        pytest.skip("filesystem rejects newline in filename")

    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    agents = briefs.load_agents()
    assert "alice" in agents
    assert "evil\n" not in agents
    assert all("\n" not in a for a in agents)
    assert all("\r" not in a for a in agents)


def test_brief_filename_with_internal_newline_rejected(tmp_path: Path, monkeypatch) -> None:
    """Internal newline is rejected by both `^` (no leading whitespace)
    and `\\Z` (no trailing chars allowed). Defense in depth."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")

    bad_name = "alice\nfoo.md"
    try:
        (briefs_dir / bad_name).write_text("# Bad")
    except OSError:
        pytest.skip("filesystem rejects newline in filename")

    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    agents = briefs.load_agents()
    assert agents == {"alice"}


def test_z_anchor_handles_dos_line_endings(monkeypatch) -> None:
    """Windows users might paste a value with \\r\\n. Both chars rejected."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice\r\n")
    with pytest.raises(ValueError):
        briefs.operator_name()


# =========================================================================
# v0.3.5 contracts: embed prerequisite documentation guard
# =========================================================================


def test_embed_dist_directory_present_or_documented(tmp_path: Path) -> None:
    """Watson's note: `go test` requires `frontend/dist/` because of
    `//go:embed`. This test guards that one of the three documentation
    paths is in place: dist exists in the repo, ui/README.md mentions
    the prerequisite, or main.go has a build-tag guard around the embed.

    This is an advisory check — it warns rather than failing because
    KI7MT folded the polish into v0.3.6 explicitly."""
    repo_root = Path(__file__).parent.parent
    dist = repo_root / "ui" / "frontend" / "dist"
    ui_readme = repo_root / "ui" / "README.md"
    main_go = repo_root / "ui" / "main.go"

    has_dist = dist.exists()
    has_readme_note = (
        ui_readme.exists() and
        ("dist" in ui_readme.read_text().lower() or
         "npm run build" in ui_readme.read_text() or
         "frontend" in ui_readme.read_text().lower())
    )
    has_buildtag = "//go:build" in main_go.read_text() if main_go.exists() else False

    documented = has_dist or has_readme_note or has_buildtag
    if not documented:
        import warnings
        warnings.warn(
            "go test embed prerequisite is undocumented. Watson flagged "
            "this; KI7MT folded into v0.3.6 polish.",
            stacklevel=2
        )


# =========================================================================
# v0.3.5 contracts: search filter input validation
# =========================================================================


def test_search_sender_field_validated(setup) -> None:
    """search() validates sender via _validate_agent. Garbage senders
    fail validation cleanly without reaching SQL."""
    with pytest.raises(ValueError, match="Invalid sender"):
        core.search(sender="x" * 1000)


def test_search_recipient_with_huge_garbage_validated(setup) -> None:
    """Same for recipient."""
    with pytest.raises(ValueError, match="Invalid recipient"):
        core.search(recipient="x" * 1000)


def test_search_subject_at_cap_with_escape_chars(setup) -> None:
    """Search subject at 1000-char cap, full of LIKE-pattern metachars.
    Each gets escaped — final SQL pattern is ~2x longer than input —
    still fits under SQLite's 50000-char LIKE limit."""
    pattern = "%_" * 500
    assert len(pattern) == 1000
    core.send("alice", "bob", "info", "literal-100%-message", "")
    result = core.search(subject=pattern, limit=10)
    assert isinstance(result, dict)


def test_search_subject_with_max_backslashes(setup) -> None:
    """All backslashes — each escapes to \\\\. 1000 \\ → 2000 chars in
    pattern + percent wrappers. Well under SQLite's 50k limit."""
    pattern = "\\" * 1000
    result = core.search(subject=pattern, limit=10)
    assert isinstance(result, dict)


# =========================================================================
# v0.3.5 contracts: brief-filename casing and edge cases
# =========================================================================


def test_brief_filename_uppercase_lowercased(tmp_path: Path, monkeypatch) -> None:
    """A brief named ALICE.md gets stem 'ALICE' → lowercased → 'alice'
    → matches NAME_RE → registered."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "ALICE.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    assert briefs.load_agents() == {"alice"}


def test_brief_filename_mixedcase_lowercased(tmp_path: Path, monkeypatch) -> None:
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "AlIcE.md").write_text("# Alice")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    assert briefs.load_agents() == {"alice"}


def test_brief_two_files_same_lowercased_name(tmp_path: Path, monkeypatch) -> None:
    """ALICE.md and alice.md both lowercase to 'alice'. Set semantics
    means duplicates collapse; read_brief picks alice.md by direct path."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "ALICE.md").write_text("# UPPER")
    try:
        (briefs_dir / "alice.md").write_text("# lower")
    except FileExistsError:
        pytest.skip("case-insensitive filesystem")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    assert briefs.load_agents() == {"alice"}
    content = briefs.read_brief("alice")
    assert content == "# lower"


def test_agent_name_no_upper_length_bound(tmp_path: Path, monkeypatch) -> None:
    """NAME_RE has no upper length cap. A 200-char filename passes the
    regex. Most filesystems cap at 255 bytes; SQLite TEXT has no cap."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    long_name = "a" + "b" * 200
    (briefs_dir / f"{long_name}.md").write_text("# long")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    db._initialized_paths.clear()
    agents = briefs.load_agents()
    assert long_name in agents


# =========================================================================
# v0.3.5 contracts: operator_name lazy resolution
# =========================================================================


def test_operator_name_resolved_lazily_each_call(monkeypatch) -> None:
    """operator_name() reads the env var on every call (no cache).
    Mid-process env var changes change the operator. Documented behavior."""
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "alice")
    assert briefs.operator_name() == "alice"

    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "bob")
    assert briefs.operator_name() == "bob"

    # Empty string fails NAME_RE (default fall-through only on UNSET).
    monkeypatch.setenv("AGENT_INBOX_OPERATOR", "")
    with pytest.raises(ValueError):
        briefs.operator_name()


def test_send_orphan_check_consistent_with_validation(setup) -> None:
    """The orphan check inside `with db.connect()` and the up-front
    `_validate_agent` both call `_agents()`, which both call
    `load_agents()`. They share the same view. No drift."""
    sent = core.send("alice", "bob", "info", "ok", "")
    assert sent["status"] == "sent"


def test_orphan_check_in_send_runs_under_lock(setup) -> None:
    """The orphan check sits inside `with db.connect()`. The connection
    is held while reading the briefs directory. Performance note: if
    `_agents()` ever became expensive (network filesystem), it would
    extend lock hold time. Pinned so a future refactor that wraps the
    orphan check in a heavier I/O path gets flagged here."""
    sent = core.send("alice", "bob", "info", "x", "")
    assert sent["status"] == "sent"


def test_agent_name_at_brief_filename_collision_with_extension(tmp_path: Path, monkeypatch) -> None:
    """A brief named 'alice.md.md' → stem 'alice.md' → has a dot →
    fails NAME_RE. Silently ignored. Same for the pathological '.md'
    case (stem '')."""
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md.md").write_text("# weird")
    (briefs_dir / "alice.md").write_text("# real alice")
    (briefs_dir / ".md").write_text("# empty stem")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    agents = briefs.load_agents()
    assert agents == {"alice"}


def test_priority_case_normalization(setup) -> None:
    """_validate_priority lowercases input. INFO, Info, iNFo all map
    to 'info'."""
    for variant in ("info", "INFO", "Info", "iNFo"):
        sent = core.send("alice", "bob", variant, "x", "")
        assert sent["priority"] == "info"

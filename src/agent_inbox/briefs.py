"""Agent registry derived from markdown brief files.

Each `*.md` file in the briefs directory registers one agent. The filename
(without `.md`) is the agent's canonical name. Names must match
`^[a-z][a-z0-9_-]*$`. The reserved name `all` is the broadcast target and
must not be used as a brief filename.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from platformdirs import user_config_dir

# `\Z` (strict end-of-string) instead of `$` because Python's `$` anchor
# matches before a final `\n` by default — `NAME_RE.match("alice\n")` would
# return a match with `$`, which violates the documented contract and
# breaks parity with Go's stricter `regexp` package. `\Z` is unambiguous.
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*\Z")
RESERVED = {"all"}
APP_NAME = "agent-inbox"


def briefs_dir() -> Path:
    """Resolve the briefs directory.

    Order: `AGENT_INBOX_BRIEFS` env var, then the OS-appropriate user config
    directory (`~/.config/agent-inbox/briefs/` on Linux,
    `~/Library/Application Support/agent-inbox/briefs/` on macOS,
    `%APPDATA%\\agent-inbox\\briefs\\` on Windows).
    """
    custom = os.environ.get("AGENT_INBOX_BRIEFS")
    if custom:
        return Path(custom).expanduser()
    return Path(user_config_dir(APP_NAME)) / "briefs"


def operator_name() -> str:
    """Return the canonical operator name (the human user).

    Validates AGENT_INBOX_OPERATOR against the same constraints as a
    brief filename: it must match `NAME_RE` and must not collide with a
    reserved name like `all`. Bad config is rejected loudly here rather
    than producing a quietly-broken installation (e.g.,
    `AGENT_INBOX_OPERATOR=all` would otherwise let any agent send as
    `all` and prevent the operator from receiving direct mail).
    """
    raw = os.environ.get("AGENT_INBOX_OPERATOR", "operator").lower()
    if raw in RESERVED:
        raise ValueError(
            f"AGENT_INBOX_OPERATOR cannot be a reserved name "
            f"(got {raw!r}; reserved: {sorted(RESERVED)})"
        )
    if not NAME_RE.match(raw):
        raise ValueError(
            f"AGENT_INBOX_OPERATOR={raw!r} doesn't match {NAME_RE.pattern} — "
            "use lowercase letters/digits/hyphen/underscore, starting with a letter."
        )
    return raw


def load_agents(directory: Path | None = None) -> set[str]:
    """Return the set of valid agent names found in the briefs directory.

    Files whose stem does not match `NAME_RE`, or matches a reserved name,
    are skipped silently.
    """
    d = directory or briefs_dir()
    if not d.exists() or not d.is_dir():
        return set()
    agents: set[str] = set()
    for path in d.glob("*.md"):
        name = path.stem.lower()
        if name in RESERVED or not NAME_RE.match(name):
            continue
        agents.add(name)
    return agents


def read_brief(name: str, directory: Path | None = None) -> str | None:
    """Return the markdown content of an agent's brief, or None if missing."""
    d = directory or briefs_dir()
    path = d / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")

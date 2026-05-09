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

NAME_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
RESERVED = {"all"}


def briefs_dir() -> Path:
    """Resolve the briefs directory.

    Order: `AGENT_INBOX_BRIEFS` env var, then `$XDG_CONFIG_HOME/agent-inbox/briefs`,
    falling back to `~/.config/agent-inbox/briefs`.
    """
    custom = os.environ.get("AGENT_INBOX_BRIEFS")
    if custom:
        return Path(custom).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "agent-inbox" / "briefs"


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

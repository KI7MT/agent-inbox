"""SQLite storage for the agent inbox.

Single file, WAL mode, parameterized queries throughout. Schema is created
idempotently on first connect.
"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('info','action','urgent')),
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK(status IN ('unread','read','approved','rejected','in_progress','done')),
    subject TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recipient_status ON messages(recipient, status);
CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp);
"""

VALID_PRIORITIES = {"info", "action", "urgent"}
VALID_STATUSES = {"unread", "read", "approved", "rejected", "in_progress", "done"}


def db_path() -> Path:
    """Resolve the SQLite database path.

    Order: `AGENT_INBOX_DB` env var, then `$XDG_DATA_HOME/agent-inbox/inbox.db`,
    falling back to `~/.local/share/agent-inbox/inbox.db`.
    """
    custom = os.environ.get("AGENT_INBOX_DB")
    if custom:
        return Path(custom).expanduser()
    base = os.environ.get("XDG_DATA_HOME") or "~/.local/share"
    return Path(base).expanduser() / "agent-inbox" / "inbox.db"


def auto_approve() -> bool:
    return os.environ.get("AGENT_INBOX_AUTO_APPROVE") == "1"


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    try:
        yield conn
    finally:
        conn.close()


def insert_message(
    conn: sqlite3.Connection,
    sender: str,
    recipient: str,
    priority: str,
    subject: str,
    body: str,
) -> tuple[str, str]:
    """Insert a message and return (id, status).

    When AGENT_INBOX_AUTO_APPROVE=1, action/urgent messages start in
    `approved` status — useful for single-user setups where the human
    is already the operator and doesn't want a manual gate.
    """
    msg_id = str(uuid.uuid4())
    if auto_approve() and priority in {"action", "urgent"}:
        status = "approved"
    else:
        status = "unread"
    conn.execute(
        "INSERT INTO messages (id, sender, recipient, priority, subject, body, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (msg_id, sender, recipient, priority, subject, body, status),
    )
    conn.commit()
    return msg_id, status


def list_for_recipient(conn: sqlite3.Connection, recipient: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, timestamp, sender, priority, status, subject "
        "FROM messages "
        "WHERE recipient IN (?, 'all') AND status IN ('unread','approved') "
        "ORDER BY timestamp",
        (recipient,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_message(conn: sqlite3.Connection, msg_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    return dict(row) if row else None


def update_status(conn: sqlite3.Connection, msg_id: str, status: str) -> int:
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status: {status!r}")
    cur = conn.execute(
        "UPDATE messages SET status = ? WHERE id = ?",
        (status, msg_id),
    )
    conn.commit()
    return cur.rowcount


def search(
    conn: sqlite3.Connection,
    sender: str,
    recipient: str,
    subject: str,
    days: int,
    limit: int,
) -> list[dict[str, Any]]:
    where = ["timestamp >= datetime('now', ?)"]
    params: list[Any] = [f"-{max(1, min(days, 365))} days"]
    if sender:
        where.append("sender = ?")
        params.append(sender)
    if recipient:
        where.append("recipient = ?")
        params.append(recipient)
    if subject:
        where.append("subject LIKE ?")
        params.append(f"%{subject}%")
    cap = max(1, min(limit, 100))
    sql = (
        "SELECT id, timestamp, sender, recipient, priority, status, subject "
        "FROM messages WHERE " + " AND ".join(where) + " "
        "ORDER BY timestamp DESC LIMIT ?"
    )
    params.append(cap)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

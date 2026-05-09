"""SQLite storage for the agent inbox.

Single file, WAL mode, parameterized queries throughout. Schema is created
idempotently on first connect; missing columns are added in place so older
inbox files keep working as the schema evolves.

Concurrency model
-----------------
Multiple processes (MCP servers, the UI, the CLI) read and write the same
SQLite file. WAL allows unlimited concurrent readers; writers serialize
globally. We rely on:

* `journal_mode=WAL` — readers don't block writers, writers don't block
  readers
* `busy_timeout=5000` — SQLite waits up to 5s internally before raising
  SQLITE_BUSY
* `synchronous=NORMAL` — durable under WAL, ~5x faster than FULL
* Connection-per-operation — short-lived locks, fast release
* `_retry_on_lock` wrapping writes — handles the rare SQLITE_LOCKED that
  busy_timeout doesn't cover (intra-connection contention, schema races)
"""

from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Iterator, TypeVar

from platformdirs import user_data_dir

T = TypeVar("T")

BUSY_TIMEOUT_MS = 5000
WRITE_RETRY_MAX = 3
WRITE_RETRY_BASE_DELAY = 0.025

# Per-process schema-init cache. Migration runs once per (process, db_path)
# so high-concurrency callers don't all funnel through BEGIN IMMEDIATE on
# every connect(). Cross-process safety is still provided by _migrate's
# own BEGIN IMMEDIATE + idempotent ALTER guards.
_init_lock = threading.Lock()
_initialized_paths: set[str] = set()

APP_NAME = "agent-inbox"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_unix INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER)),
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('info','action','urgent')),
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK(status IN ('unread','read','approved','rejected','in_progress','done')),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    parent_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_recipient_status ON messages(recipient, status);
CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_created_unix ON messages(created_unix);
CREATE INDEX IF NOT EXISTS idx_parent_id ON messages(parent_id);
"""

VALID_PRIORITIES = {"info", "action", "urgent"}
VALID_STATUSES = {"unread", "read", "approved", "rejected", "in_progress", "done"}


def db_path() -> Path:
    """Resolve the SQLite database path.

    Order: `AGENT_INBOX_DB` env var, then the OS-appropriate user data
    directory (`~/.local/share/agent-inbox/inbox.db` on Linux,
    `~/Library/Application Support/agent-inbox/inbox.db` on macOS,
    `%LOCALAPPDATA%\\agent-inbox\\inbox.db` on Windows).
    """
    custom = os.environ.get("AGENT_INBOX_DB")
    if custom:
        return Path(custom).expanduser()
    return Path(user_data_dir(APP_NAME)) / "inbox.db"


def auto_approve() -> bool:
    return os.environ.get("AGENT_INBOX_AUTO_APPROVE") == "1"


def _is_lock_error(exc: BaseException) -> bool:
    """True if `exc` looks like a SQLite locking conflict worth retrying."""
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    msg = str(exc).lower()
    return "locked" in msg or "busy" in msg


def _retry_on_lock(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator: retry `func` on SQLITE_LOCKED / SQLITE_BUSY with backoff.

    busy_timeout already handles inter-connection writer contention; this
    handles the residual intra-connection cases (e.g., a long-running read
    transaction holds a shared lock when a write tries to upgrade).
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> T:
        last_exc: BaseException | None = None
        for attempt in range(WRITE_RETRY_MAX + 1):
            try:
                return func(*args, **kwargs)
            except sqlite3.OperationalError as exc:
                if not _is_lock_error(exc):
                    raise
                last_exc = exc
                if attempt == WRITE_RETRY_MAX:
                    break
                delay = WRITE_RETRY_BASE_DELAY * (2 ** attempt)
                delay += random.uniform(0, delay * 0.25)  # jitter
                time.sleep(delay)
        assert last_exc is not None
        raise last_exc

    return wrapper


@_retry_on_lock
def _migrate(conn: sqlite3.Connection) -> None:
    """Idempotent additive migrations.

    Concurrency note: when two fresh processes open the DB simultaneously
    they would otherwise race — both read `PRAGMA table_info`, both see
    "column missing", both try `ALTER TABLE ADD COLUMN`, one wins and the
    other gets a "duplicate column" error that isn't a lock error.

    `BEGIN IMMEDIATE` acquires the writer lock at entry so concurrent
    migrators serialize. We re-check inside the transaction in case a
    parallel process won the race and already added the columns.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()}
        if "parent_id" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN parent_id TEXT")
        if "created_unix" not in cols:
            conn.execute("ALTER TABLE messages ADD COLUMN created_unix INTEGER")
            conn.execute(
                "UPDATE messages SET created_unix = "
                "CAST(strftime('%s', timestamp) AS INTEGER) WHERE created_unix IS NULL"
            )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_unix ON messages(created_unix)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_parent_id ON messages(parent_id)")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


@_retry_on_lock
def _ensure_wal(conn: sqlite3.Connection) -> None:
    """Switch the database to WAL journal mode if it isn't already.

    journal_mode=WAL is sticky on the file — once any process has set it,
    every later connection sees WAL on open with no exclusive lock needed.
    The first process to touch a fresh DB has to grab EXCLUSIVE to do the
    switch, and that EXCLUSIVE can be contested by other processes opening
    the file simultaneously. busy_timeout doesn't always cover that case,
    so we retry. Subsequent calls are cheap no-ops because the check is
    read-only.
    """
    cur = conn.execute("PRAGMA journal_mode").fetchone()
    if cur and str(cur[0]).lower() == "wal":
        return
    result = conn.execute("PRAGMA journal_mode=WAL").fetchone()
    if not result or str(result[0]).lower() != "wal":
        raise sqlite3.OperationalError(
            "could not switch to WAL mode (database busy)"
        )


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    p_str = str(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p_str, timeout=BUSY_TIMEOUT_MS / 1000.0)
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    if p_str not in _initialized_paths:
        with _init_lock:
            if p_str not in _initialized_paths:
                _ensure_wal(conn)
                conn.executescript(SCHEMA)
                _migrate(conn)
                _initialized_paths.add(p_str)
    try:
        yield conn
    finally:
        conn.close()


@_retry_on_lock
def insert_message(
    conn: sqlite3.Connection,
    sender: str,
    recipient: str,
    priority: str,
    subject: str,
    body: str,
    parent_id: str | None = None,
) -> tuple[str, str]:
    """Insert a message and return (id, status)."""
    msg_id = str(uuid.uuid4())
    if auto_approve() and priority in {"action", "urgent"}:
        status = "approved"
    else:
        status = "unread"
    conn.execute(
        "INSERT INTO messages "
        "(id, sender, recipient, priority, subject, body, status, parent_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (msg_id, sender, recipient, priority, subject, body, status, parent_id),
    )
    conn.commit()
    return msg_id, status


def list_for_recipient(conn: sqlite3.Connection, recipient: str) -> list[dict[str, Any]]:
    """Return messages a recipient should act on right now.

    Approval gate: action/urgent messages only become visible to the
    recipient after the operator has flipped them to `approved`. Until
    then they live in the operator's pending queue alone. info messages
    are act-on-immediately so they show up while still unread.
    """
    rows = conn.execute(
        "SELECT id, timestamp, sender, priority, status, subject, parent_id "
        "FROM messages "
        "WHERE recipient IN (?, 'all') "
        "  AND ( "
        "    (status = 'unread' AND priority = 'info') "
        "    OR status = 'approved' "
        "  ) "
        "ORDER BY created_unix",
        (recipient,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_message(conn: sqlite3.Connection, msg_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (msg_id,)).fetchone()
    return dict(row) if row else None


@_retry_on_lock
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
        "ORDER BY created_unix DESC LIMIT ?"
    )
    params.append(cap)
    rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_pending_approval(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Return action/urgent messages still waiting for operator approval.

    Ordered urgent-first, then action, oldest within each priority.
    """
    rows = conn.execute(
        "SELECT id, timestamp, sender, recipient, priority, status, subject, parent_id "
        "FROM messages "
        "WHERE status = 'unread' AND priority IN ('action', 'urgent') "
        "ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'action' THEN 1 ELSE 2 END, "
        "         created_unix"
    ).fetchall()
    return [dict(r) for r in rows]


def list_recent(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT id, timestamp, sender, recipient, priority, status, subject "
        "FROM messages ORDER BY created_unix DESC LIMIT ?",
        (max(1, min(limit, 500)),),
    ).fetchall()
    return [dict(r) for r in rows]

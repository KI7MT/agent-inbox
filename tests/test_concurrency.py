"""Concurrency tests — verify multiple threads/processes can write safely.

These don't prove there are zero conflicts under all loads; they prove the
PRAGMA settings + retry decorator handle realistic contention without
losing writes or surfacing SQLITE_BUSY to the caller.
"""

from __future__ import annotations

import multiprocessing as mp
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from agent_inbox import core, db


@pytest.fixture
def briefs_and_db(tmp_path: Path, monkeypatch):
    briefs_dir = tmp_path / "briefs"
    briefs_dir.mkdir()
    (briefs_dir / "alice.md").write_text("# Alice")
    (briefs_dir / "bob.md").write_text("# Bob")
    monkeypatch.setenv("AGENT_INBOX_BRIEFS", str(briefs_dir))
    monkeypatch.setenv("AGENT_INBOX_DB", str(tmp_path / "inbox.db"))
    return tmp_path / "inbox.db"


def test_pragmas_are_set(briefs_and_db: Path) -> None:
    with db.connect() as conn:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        busy = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    assert journal == "wal"
    assert busy == 5000
    # synchronous=NORMAL is value 1
    assert sync == 1


def test_concurrent_threaded_writers(briefs_and_db: Path) -> None:
    """20 threads x 5 messages each = 100 inserts, no failures, no losses."""
    threads = 20
    per_thread = 5

    def writer(idx: int) -> None:
        for n in range(per_thread):
            core.send("alice", "bob", "info", f"t{idx}-m{n}", "")

    workers = [threading.Thread(target=writer, args=(i,)) for i in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=30)
        assert not w.is_alive(), "writer thread hung"

    result = core.list_recent(limit=500)
    assert result["count"] == threads * per_thread


def test_reads_dont_block_writes(briefs_and_db: Path) -> None:
    """A long-running reader doesn't prevent writers from progressing.

    WAL's central guarantee — if this fails, WAL isn't engaged.
    """
    # Seed
    for n in range(10):
        core.send("alice", "bob", "info", f"seed-{n}", "")

    stop = threading.Event()
    reader_iters = [0]

    def reader() -> None:
        while not stop.is_set():
            with db.connect() as conn:
                conn.execute("BEGIN").fetchall()
                conn.execute("SELECT count(*) FROM messages").fetchone()
                # Hold the read transaction briefly
                time.sleep(0.05)
                conn.execute("COMMIT")
            reader_iters[0] += 1

    r = threading.Thread(target=reader, daemon=True)
    r.start()

    started = time.monotonic()
    write_count = 0
    while time.monotonic() - started < 1.0:
        core.send("alice", "bob", "info", f"contended-{write_count}", "")
        write_count += 1
    stop.set()
    r.join(timeout=5)

    # Threshold is intentionally low (2 each) — the test asserts that
    # neither side is *blocked*, not that they're fast. CI runners vary
    # widely (Windows / macOS hosted runners are slower than Linux), so
    # any positive count > 1 demonstrates concurrent progress.
    assert write_count >= 2, f"only {write_count} writes completed under read load"
    assert reader_iters[0] >= 2, f"reader only completed {reader_iters[0]} cycles"


def _process_writer(db_path: str, briefs_dir: str, idx: int, count: int) -> tuple[int, str]:
    """Run in a subprocess — fresh interpreter, no shared sqlite connection.

    Returns (sent_count, error_message). error_message is empty on success.
    """
    import os
    import traceback

    os.environ["AGENT_INBOX_DB"] = db_path
    os.environ["AGENT_INBOX_BRIEFS"] = briefs_dir

    from agent_inbox import core as _core

    sent = 0
    for n in range(count):
        try:
            _core.send("alice", "bob", "info", f"p{idx}-m{n}", "")
            sent += 1
        except sqlite3.OperationalError:
            return sent, traceback.format_exc()
    return sent, ""


def test_concurrent_multiprocess_writers(briefs_and_db: Path) -> None:
    """5 processes x 10 messages each = 50 inserts via fork/spawn.

    Skips on platforms where multiprocessing is unreliable in pytest.
    """
    procs = 5
    per_proc = 10

    db_path = str(briefs_and_db)
    briefs_dir = str(briefs_and_db.parent / "briefs")

    ctx = mp.get_context("spawn")
    with ctx.Pool(processes=procs) as pool:
        results = pool.starmap(
            _process_writer,
            [(db_path, briefs_dir, i, per_proc) for i in range(procs)],
        )

    failures = [(i, sent, err) for i, (sent, err) in enumerate(results) if err]
    if failures:
        details = "\n".join(f"proc {i}: sent={sent}, err={err}" for i, sent, err in failures)
        pytest.fail(f"{len(failures)} subprocess(es) failed:\n{details}")

    sent_counts = [sent for sent, _ in results]
    assert all(s == per_proc for s in sent_counts), f"counts: {sent_counts}"

    result = core.list_recent(limit=500)
    assert result["count"] == procs * per_proc


def test_write_retry_decorator_eventually_gives_up(briefs_and_db: Path) -> None:
    """If the lock truly never releases, the decorator surfaces the error
    after exhausting retries — not an infinite loop."""
    from agent_inbox.db import _retry_on_lock

    attempts = {"count": 0}

    @_retry_on_lock
    def always_locked() -> None:
        attempts["count"] += 1
        raise sqlite3.OperationalError("database is locked")

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        always_locked()
    # 1 initial + WRITE_RETRY_MAX retries
    assert attempts["count"] == db.WRITE_RETRY_MAX + 1


def test_write_retry_skips_non_lock_errors(briefs_and_db: Path) -> None:
    """Non-lock errors propagate immediately, no retry."""
    from agent_inbox.db import _retry_on_lock

    attempts = {"count": 0}

    @_retry_on_lock
    def schema_error() -> None:
        attempts["count"] += 1
        raise sqlite3.OperationalError("no such table: nonexistent")

    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        schema_error()
    assert attempts["count"] == 1

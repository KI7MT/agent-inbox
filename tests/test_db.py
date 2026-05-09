from pathlib import Path

from agent_inbox import db


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "inbox.db"
    with db.connect(path) as conn:
        msg_id, status = db.insert_message(
            conn, "alice", "bob", "info", "hi", "hello bob"
        )
        assert status == "unread"
        msg = db.get_message(conn, msg_id)
        assert msg is not None
        assert msg["sender"] == "alice"
        assert msg["recipient"] == "bob"
        assert msg["status"] == "unread"
        assert msg["body"] == "hello bob"


def test_list_for_recipient_includes_broadcast(tmp_path: Path) -> None:
    path = tmp_path / "inbox.db"
    with db.connect(path) as conn:
        db.insert_message(conn, "alice", "bob", "info", "direct", "")
        db.insert_message(conn, "alice", "all", "info", "broadcast", "")
        db.insert_message(conn, "alice", "carol", "info", "not for bob", "")
        rows = db.list_for_recipient(conn, "bob")
        subjects = {r["subject"] for r in rows}
        assert subjects == {"direct", "broadcast"}


def test_update_status(tmp_path: Path) -> None:
    path = tmp_path / "inbox.db"
    with db.connect(path) as conn:
        msg_id, _ = db.insert_message(conn, "alice", "bob", "info", "s", "b")
        n = db.update_status(conn, msg_id, "done")
        assert n == 1
        msg = db.get_message(conn, msg_id)
        assert msg is not None
        assert msg["status"] == "done"


def test_search_filters(tmp_path: Path) -> None:
    path = tmp_path / "inbox.db"
    with db.connect(path) as conn:
        db.insert_message(conn, "alice", "bob", "info", "release v1", "")
        db.insert_message(conn, "alice", "bob", "info", "lunch?", "")
        db.insert_message(conn, "carol", "bob", "urgent", "release v2", "")
        all_rows = db.search(conn, "", "", "", days=7, limit=20)
        assert len(all_rows) == 3
        only_alice = db.search(conn, "alice", "", "", days=7, limit=20)
        assert {r["sender"] for r in only_alice} == {"alice"}
        release_only = db.search(conn, "", "", "release", days=7, limit=20)
        assert {r["subject"] for r in release_only} == {"release v1", "release v2"}


def test_auto_approve(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AGENT_INBOX_AUTO_APPROVE", "1")
    path = tmp_path / "inbox.db"
    with db.connect(path) as conn:
        _, status_info = db.insert_message(conn, "a", "b", "info", "", "")
        _, status_action = db.insert_message(conn, "a", "b", "action", "", "")
        _, status_urgent = db.insert_message(conn, "a", "b", "urgent", "", "")
        assert status_info == "unread"
        assert status_action == "approved"
        assert status_urgent == "approved"

"""Plain-function inbox operations — no MCP framework coupling.

`server.py` wraps these as MCP tools. `cli.py` wraps them as a command-line
interface for the human operator. Tests import this module directly.
"""

from __future__ import annotations

import time
from typing import Any

from agent_inbox import briefs, db

VALID_PRIORITIES = {"info", "action", "urgent"}
AGENT_SETTABLE_STATUSES = {"read", "in_progress", "done"}
RESERVED_STATUSES = {"approved", "rejected"}
BROADCAST = "all"

# Bounds on user-supplied strings. Subjects are short by convention; bodies
# are markdown-flavored prose, so 1 MB is generous but still bounded so a
# pathological agent can't fill the disk by sending huge messages.
MAX_SUBJECT_LEN = 500
MAX_BODY_LEN = 1_000_000

WAIT_POLL_INTERVAL = 1.0
WAIT_MAX_SECONDS = 300
WAIT_DEFAULT_SECONDS = 30


def _agents() -> set[str]:
    return briefs.load_agents()


def _validate_agent(name: str, field: str, allow_broadcast: bool = False) -> str:
    n = name.lower()
    valid = _agents()
    if allow_broadcast:
        valid = valid | {BROADCAST}
    if n not in valid:
        listing = ", ".join(sorted(valid)) if valid else "(no briefs found — see briefs directory)"
        raise ValueError(
            f"Invalid {field}: '{name}'. Must be one of: {listing}. "
            "Add a brief file to register a new agent."
        )
    return n


def _validate_priority(priority: str) -> str:
    p = priority.lower()
    if p not in VALID_PRIORITIES:
        raise ValueError(
            f"Invalid priority: '{priority}'. "
            f"Must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
        )
    return p


def _validate_lengths(subject: str, body: str) -> None:
    if len(subject) > MAX_SUBJECT_LEN:
        raise ValueError(
            f"Subject too long: {len(subject)} chars (max {MAX_SUBJECT_LEN})."
        )
    if len(body) > MAX_BODY_LEN:
        raise ValueError(
            f"Body too long: {len(body)} chars (max {MAX_BODY_LEN})."
        )


def list_agents() -> dict[str, Any]:
    return {
        "briefs_dir": str(briefs.briefs_dir()),
        "operator": briefs.operator_name(),
        "agents": sorted(_agents()),
    }


def check(recipient: str) -> dict[str, Any]:
    r = _validate_agent(recipient, "recipient")
    with db.connect() as conn:
        rows = db.list_for_recipient(conn, r)
    unread = sum(1 for row in rows if row["status"] == "unread")
    approved = sum(1 for row in rows if row["status"] == "approved")
    return {
        "recipient": r,
        "unread_count": unread,
        "approved_count": approved,
        "messages": rows,
    }


def read(message_id: str) -> dict[str, Any]:
    with db.connect() as conn:
        msg = db.get_message(conn, message_id)
    return msg if msg else {"error": f"Message {message_id} not found."}


def send(
    sender: str,
    recipient: str,
    priority: str,
    subject: str,
    body: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    """Send a message. Broadcasts (recipient='all') fan out at send time.

    Fan-out semantics: a broadcast becomes one independent message per
    registered agent (excluding the sender). Each recipient gets their
    own row, their own status, their own approval state. This avoids the
    "one row, global state" trap where one recipient's `mark` mutates
    every other recipient's view.

    The sender is excluded from the fan-out (you don't deliver your own
    broadcast back to yourself).
    """
    s = _validate_agent(sender, "sender")
    r = _validate_agent(recipient, "recipient", allow_broadcast=True)
    p = _validate_priority(priority)
    _validate_lengths(subject, body)

    if r == BROADCAST:
        targets = sorted(_agents() - {s})
        if not targets:
            return {
                "status": "no_recipients",
                "from": s,
                "to": r,
                "priority": p,
                "subject": subject,
                "broadcast_to": [],
                "ids": [],
            }
        ids: list[str] = []
        initial: str | None = None
        with db.connect() as conn:
            for target in targets:
                msg_id, status = db.insert_message(conn, s, target, p, subject, body, parent_id)
                ids.append(msg_id)
                initial = status
        return {
            "status": "sent",
            "from": s,
            "to": r,
            "priority": p,
            "subject": subject,
            "broadcast_to": targets,
            "ids": ids,
            "initial_state": initial,
            **({"parent_id": parent_id} if parent_id else {}),
        }

    with db.connect() as conn:
        msg_id, status = db.insert_message(conn, s, r, p, subject, body, parent_id)
    return {
        "status": "sent",
        "id": msg_id,
        "from": s,
        "to": r,
        "priority": p,
        "subject": subject,
        "initial_state": status,
        **({"parent_id": parent_id} if parent_id else {}),
    }


def mark(message_id: str, status: str) -> dict[str, Any]:
    s = status.lower()
    if s in RESERVED_STATUSES:
        raise ValueError(
            f"Status '{s}' is reserved for the human reviewer (set via UI or CLI). "
            f"Agents may use: {', '.join(sorted(AGENT_SETTABLE_STATUSES))}"
        )
    if s not in AGENT_SETTABLE_STATUSES:
        raise ValueError(
            f"Invalid status: '{status}'. "
            f"Must be one of: {', '.join(sorted(AGENT_SETTABLE_STATUSES))}"
        )
    with db.connect() as conn:
        n = db.update_status(conn, message_id, s)
    if n == 0:
        return {"error": f"Message {message_id} not found."}
    return {"status": "updated", "message_id": message_id, "new_status": s}


def search(
    sender: str = "",
    recipient: str = "",
    subject: str = "",
    days: int = 7,
    limit: int = 20,
) -> dict[str, Any]:
    s = _validate_agent(sender, "sender") if sender else ""
    r = _validate_agent(recipient, "recipient", allow_broadcast=True) if recipient else ""
    with db.connect() as conn:
        rows = db.search(conn, s, r, subject, days, limit)
    return {"count": len(rows), "messages": rows}


def brief(name: str) -> dict[str, Any]:
    """Return the markdown brief content for an agent.

    Useful before sending a message to an agent you haven't worked with yet.
    """
    n = _validate_agent(name, "agent")
    content = briefs.read_brief(n)
    if content is None:
        return {"error": f"Brief for '{n}' could not be read."}
    return {"agent": n, "brief": content}


def wait(recipient: str, timeout_seconds: int = WAIT_DEFAULT_SECONDS) -> dict[str, Any]:
    """Block until pending messages exist for `recipient`, or timeout.

    Returns immediately with any unread/approved messages already waiting.
    Otherwise polls the DB on a short interval until something arrives or
    the timeout elapses. Designed for agents that should sit idle and react
    to incoming mail without the operator prompting them.
    """
    r = _validate_agent(recipient, "recipient")
    cap = max(1, min(timeout_seconds, WAIT_MAX_SECONDS))
    deadline = time.monotonic() + cap
    while True:
        with db.connect() as conn:
            rows = db.list_for_recipient(conn, r)
        if rows:
            unread = sum(1 for row in rows if row["status"] == "unread")
            approved = sum(1 for row in rows if row["status"] == "approved")
            return {
                "recipient": r,
                "timed_out": False,
                "unread_count": unread,
                "approved_count": approved,
                "messages": rows,
            }
        if time.monotonic() >= deadline:
            return {
                "recipient": r,
                "timed_out": True,
                "unread_count": 0,
                "approved_count": 0,
                "messages": [],
            }
        time.sleep(WAIT_POLL_INTERVAL)


def operator_set_status(message_id: str, status: str) -> dict[str, Any]:
    """Operator-only path for `approved` and `rejected`.

    The MCP-facing `mark()` blocks these statuses so agents cannot self-approve.
    The operator CLI calls this instead.
    """
    s = status.lower()
    if s not in db.VALID_STATUSES:
        raise ValueError(f"Invalid status: '{status}'.")
    with db.connect() as conn:
        n = db.update_status(conn, message_id, s)
    if n == 0:
        return {"error": f"Message {message_id} not found."}
    return {"status": "updated", "message_id": message_id, "new_status": s}


def list_recent(limit: int = 50) -> dict[str, Any]:
    with db.connect() as conn:
        rows = db.list_recent(conn, limit)
    return {"count": len(rows), "messages": rows}


def list_pending_approval() -> dict[str, Any]:
    """Operator's approval queue — unread action/urgent messages."""
    with db.connect() as conn:
        rows = db.list_pending_approval(conn)
    return {"count": len(rows), "messages": rows}


def reply(
    sender: str,
    in_reply_to: str,
    body: str,
    priority: str = "info",
) -> dict[str, Any]:
    """Reply to a message you received.

    The reply goes back to the original sender, with `parent_id` set to
    the message being replied to and the subject prefixed with `Re: `
    (unless it already starts with `re:`). The replier must be the
    original recipient — or the original message must be a broadcast.
    """
    s = _validate_agent(sender, "sender")
    p = _validate_priority(priority)
    _validate_lengths("", body)  # subject inherited from parent, just check body
    with db.connect() as conn:
        parent = db.get_message(conn, in_reply_to)
        if not parent:
            return {"error": f"Parent message {in_reply_to} not found."}
        if parent["recipient"] != s and parent["recipient"] != BROADCAST:
            raise ValueError(
                f"Cannot reply: '{s}' was not the recipient of message "
                f"{in_reply_to} (sent to '{parent['recipient']}')."
            )
        recipient = parent["sender"].lower()
        subject = parent["subject"]
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"
        msg_id, status = db.insert_message(
            conn, s, recipient, p, subject, body, in_reply_to
        )
    return {
        "status": "sent",
        "id": msg_id,
        "from": s,
        "to": recipient,
        "priority": p,
        "subject": subject,
        "initial_state": status,
        "parent_id": in_reply_to,
    }

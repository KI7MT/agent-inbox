"""Plain-function inbox operations — no MCP framework coupling.

`server.py` wraps these as MCP tools. Tests import this module directly.
"""

from __future__ import annotations

from typing import Any

from agent_inbox import briefs, db

VALID_PRIORITIES = {"info", "action", "urgent"}
AGENT_SETTABLE_STATUSES = {"read", "in_progress", "done"}
RESERVED_STATUSES = {"approved", "rejected"}
BROADCAST = "all"


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


def list_agents() -> dict[str, Any]:
    return {
        "briefs_dir": str(briefs.briefs_dir()),
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


def send(sender: str, recipient: str, priority: str, subject: str, body: str) -> dict[str, Any]:
    s = _validate_agent(sender, "sender")
    r = _validate_agent(recipient, "recipient", allow_broadcast=True)
    p = _validate_priority(priority)
    with db.connect() as conn:
        msg_id, status = db.insert_message(conn, s, r, p, subject, body)
    return {
        "status": "sent",
        "id": msg_id,
        "from": s,
        "to": r,
        "priority": p,
        "subject": subject,
        "initial_state": status,
    }


def mark(message_id: str, status: str) -> dict[str, Any]:
    s = status.lower()
    if s in RESERVED_STATUSES:
        raise ValueError(
            f"Status '{s}' is reserved for the human reviewer (set via UI). "
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

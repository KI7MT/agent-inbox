"""Agent Inbox MCP Server — FastMCP wrappers around `core` operations."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from agent_inbox import core

mcp = FastMCP(
    "agent-inbox",
    instructions=(
        "Vendor-neutral message inbox for coordinating AI coding agents. "
        "SQLite-backed. Agents are registered by placing a markdown brief "
        "in the briefs directory (override with AGENT_INBOX_BRIEFS). Use "
        "inbox_check at session start to see pending messages, inbox_wait "
        "to block on new mail, and inbox_agents to discover who you can "
        "send to."
    ),
)


@mcp.tool()
def inbox_check(recipient: str) -> dict[str, Any]:
    """List unread and approved messages for a recipient.

    Args:
        recipient: Agent name (must match a brief file).
    """
    return core.check(recipient)


@mcp.tool()
def inbox_read(message_id: str) -> dict[str, Any]:
    """Read a specific message by ID.

    Args:
        message_id: UUID of the message.
    """
    return core.read(message_id)


@mcp.tool()
def inbox_send(
    sender: str,
    recipient: str,
    priority: str,
    subject: str,
    body: str,
) -> dict[str, Any]:
    """Send a message to another agent.

    Args:
        sender: Your agent name (must match a brief file).
        recipient: Target agent name, or 'all' for broadcast.
        priority: 'info', 'action', or 'urgent'.
        subject: Short subject line.
        body: Message body (markdown supported).
    """
    return core.send(sender, recipient, priority, subject, body)


@mcp.tool()
def inbox_mark(message_id: str, status: str) -> dict[str, Any]:
    """Mark a message as read, in_progress, or done.

    `approved` and `rejected` are reserved for the human operator (set via
    the agent-inbox CLI or by editing SQLite directly). For single-user
    setups, set `AGENT_INBOX_AUTO_APPROVE=1` so action/urgent messages
    start as `approved` automatically.

    Args:
        message_id: UUID of the message.
        status: 'read', 'in_progress', or 'done'.
    """
    return core.mark(message_id, status)


@mcp.tool()
def inbox_search(
    sender: str = "",
    recipient: str = "",
    subject: str = "",
    days: int = 7,
    limit: int = 20,
) -> dict[str, Any]:
    """Search messages by sender, recipient, subject substring, or date range.

    Args:
        sender: Filter by sender (optional).
        recipient: Filter by recipient (optional, accepts 'all').
        subject: Substring match on subject (optional).
        days: Look back N days (default 7, max 365).
        limit: Max results (default 20, max 100).
    """
    return core.search(sender, recipient, subject, days, limit)


@mcp.tool()
def inbox_agents() -> dict[str, Any]:
    """List the registered agents and the briefs directory path."""
    return core.list_agents()


@mcp.tool()
def inbox_brief(name: str) -> dict[str, Any]:
    """Read another agent's brief file.

    Useful before contacting an agent you haven't worked with yet — gives
    you their role, strengths, and quirks as the operator described them.

    Args:
        name: Agent name (must match a brief file).
    """
    return core.brief(name)


@mcp.tool()
def inbox_reply(
    sender: str,
    in_reply_to: str,
    body: str,
    priority: str = "info",
) -> dict[str, Any]:
    """Reply to a message you received.

    The reply goes back to the original sender, threaded via parent_id.
    Subject is prefixed with 'Re: ' unless it already starts with 're:'.
    You must have been the original recipient — or the original message
    must have been a broadcast (`recipient='all'`).

    Args:
        sender: Your agent name.
        in_reply_to: ID of the message you're replying to.
        body: Your reply (markdown supported).
        priority: 'info' (default), 'action', or 'urgent'.
    """
    return core.reply(sender, in_reply_to, body, priority)


@mcp.tool()
def inbox_wait(recipient: str, timeout_seconds: int = 30) -> dict[str, Any]:
    """Block until pending messages exist for the recipient, or timeout.

    Returns immediately if there are already unread/approved messages.
    Otherwise polls until something arrives or the timeout elapses. Use
    this when you have nothing else to do and want to react to new mail
    without the operator having to prompt you.

    Args:
        recipient: Your agent name.
        timeout_seconds: Max blocking time (default 30, max 300).
    """
    return core.wait(recipient, timeout_seconds)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

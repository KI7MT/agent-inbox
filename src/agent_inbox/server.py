"""Agent Inbox MCP Server — FastMCP wrappers around `core` operations."""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from agent_inbox import core

mcp = FastMCP(
    "agent-inbox",
    instructions=(
        "Vendor-neutral message inbox for coordinating AI coding agents on "
        "a single host. SQLite-backed. Agents are registered by placing a "
        "markdown brief in the briefs directory (default: "
        "~/.config/agent-inbox/briefs/, override with AGENT_INBOX_BRIEFS). "
        "Use inbox_check at session start to see unread and approved "
        "messages. Use inbox_agents to list who you can send to."
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

    `approved` and `rejected` are reserved for the human reviewer (set via
    UI or by editing SQLite directly). For single-user setups, set
    `AGENT_INBOX_AUTO_APPROVE=1` so action/urgent messages start as
    `approved` automatically.

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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

"""Operator CLI — `agent-inbox` command for the human user.

Subcommands:
  list      — show recent messages (or pending for one recipient)
  read      — print a message in full
  send      — send a message
  approve   — approve an action/urgent message
  reject    — reject an action/urgent message
  mark      — set a message status (read/in_progress/done)
  watch     — live tail (poll-based) for one recipient
  agents    — list registered agents
  brief     — print an agent's brief
  paths     — print resolved briefs / DB paths (for config snippets)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from agent_inbox import briefs, core, db


def _print_message_summary(m: dict[str, Any]) -> None:
    pid = f" (re: {m['parent_id'][:8]})" if m.get("parent_id") else ""
    print(
        f"  [{m['status']:11s}] {m['priority']:7s} "
        f"{m['sender']:>12s} -> {m.get('recipient', '?'):<12s} "
        f"{m['timestamp']}  {m['subject']}{pid}"
    )
    print(f"    id: {m['id']}")


def cmd_list(args: argparse.Namespace) -> int:
    if args.for_:
        result = core.check(args.for_)
        print(
            f"recipient={result['recipient']}  "
            f"unread={result['unread_count']}  approved={result['approved_count']}"
        )
        for m in result["messages"]:
            m_full = dict(m, recipient=args.for_)
            _print_message_summary(m_full)
        return 0
    result = core.list_recent(limit=args.limit)
    print(f"recent (count={result['count']}):")
    for m in result["messages"]:
        _print_message_summary(m)
    return 0


def cmd_read(args: argparse.Namespace) -> int:
    msg = core.read(args.id)
    if "error" in msg:
        print(msg["error"], file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(msg, indent=2))
        return 0
    print(f"id:        {msg['id']}")
    print(f"timestamp: {msg['timestamp']}")
    print(f"from:      {msg['sender']}")
    print(f"to:        {msg['recipient']}")
    print(f"priority:  {msg['priority']}")
    print(f"status:    {msg['status']}")
    if msg.get("parent_id"):
        print(f"in-reply-to: {msg['parent_id']}")
    print(f"subject:   {msg['subject']}")
    print()
    print(msg["body"])
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    sender = args.from_ or briefs.operator_name()
    body = args.body
    if body == "-":
        body = sys.stdin.read()
    try:
        result = core.send(sender, args.to, args.priority, args.subject, body)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if result["status"] == "no_recipients":
        print(f"no recipients (no registered agents besides {result['from']})", file=sys.stderr)
        return 1
    if result["to"] == "all":
        targets = result.get("broadcast_to", [])
        print(f"broadcast {len(result['ids'])} copies  {result['from']} -> {', '.join(targets)}")
    else:
        print(f"sent {result['id']}  {result['from']} -> {result['to']}  ({result['initial_state']})")
    return 0


def cmd_mark(args: argparse.Namespace) -> int:
    try:
        result = core.mark(args.id, args.status)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(f"{args.id}: status -> {result['new_status']}")
    return 0


def _operator_set(message_id: str, status: str) -> int:
    result = core.operator_set_status(message_id, status)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(f"{message_id}: status -> {result['new_status']}")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    return _operator_set(args.id, "approved")


def cmd_reject(args: argparse.Namespace) -> int:
    return _operator_set(args.id, "rejected")


def cmd_watch(args: argparse.Namespace) -> int:
    seen: set[str] = set()
    print(f"watching for {args.for_} (Ctrl+C to stop)...", file=sys.stderr)
    try:
        while True:
            result = core.check(args.for_)
            for m in result["messages"]:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    _print_message_summary(dict(m, recipient=args.for_))
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("", file=sys.stderr)
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    result = core.list_agents()
    print(f"briefs_dir: {result['briefs_dir']}")
    print(f"operator:   {result['operator']}")
    if not result["agents"]:
        print("(no agents registered — drop *.md files into the briefs dir)")
        return 0
    print("agents:")
    for name in result["agents"]:
        marker = "  *" if name == result["operator"] else "   "
        print(f"{marker}{name}")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    result = core.brief(args.name)
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    print(result["brief"])
    return 0


def cmd_paths(args: argparse.Namespace) -> int:
    print(f"briefs_dir: {briefs.briefs_dir()}")
    print(f"db_path:    {db.db_path()}")
    print(f"operator:   {briefs.operator_name()}")
    return 0


def cmd_pending(args: argparse.Namespace) -> int:
    result = core.list_pending_approval()
    if not result["messages"]:
        print("(no messages awaiting approval)")
        return 0
    print(f"awaiting approval (count={result['count']}):")
    for m in result["messages"]:
        _print_message_summary(m)
    return 0


def cmd_reply(args: argparse.Namespace) -> int:
    sender = args.from_ or briefs.operator_name()
    body = args.body
    if body == "-":
        body = sys.stdin.read()
    try:
        result = core.reply(sender, args.id, body, args.priority)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if "error" in result:
        print(result["error"], file=sys.stderr)
        return 1
    parent_short = result["parent_id"][:8]
    print(f"replied {result['id']}  {result['from']} -> {result['to']}  (re: {parent_short})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="agent-inbox",
        description="Operator CLI for the agent-inbox MCP server.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="Show recent messages (or pending for one recipient)")
    pl.add_argument("--for", dest="for_", help="Filter to pending mail for this agent")
    pl.add_argument("--limit", type=int, default=20)
    pl.set_defaults(func=cmd_list)

    pr = sub.add_parser("read", help="Print a message in full")
    pr.add_argument("id")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_read)

    ps = sub.add_parser("send", help="Send a message")
    ps.add_argument("--from", dest="from_", help="Sender (default: operator)")
    ps.add_argument("--to", required=True)
    ps.add_argument("--priority", default="info", choices=["info", "action", "urgent"])
    ps.add_argument("subject")
    ps.add_argument("body", help="Message body, or '-' to read from stdin")
    ps.set_defaults(func=cmd_send)

    pm = sub.add_parser("mark", help="Set status (read/in_progress/done)")
    pm.add_argument("id")
    pm.add_argument("status", choices=["read", "in_progress", "done"])
    pm.set_defaults(func=cmd_mark)

    pa = sub.add_parser("approve", help="Approve an action/urgent message")
    pa.add_argument("id")
    pa.set_defaults(func=cmd_approve)

    pj = sub.add_parser("reject", help="Reject an action/urgent message")
    pj.add_argument("id")
    pj.set_defaults(func=cmd_reject)

    pw = sub.add_parser("watch", help="Live tail pending mail for one recipient")
    pw.add_argument("--for", dest="for_", required=True)
    pw.add_argument("--interval", type=float, default=2.0)
    pw.set_defaults(func=cmd_watch)

    pg = sub.add_parser("agents", help="List registered agents")
    pg.set_defaults(func=cmd_agents)

    pb = sub.add_parser("brief", help="Print an agent's brief")
    pb.add_argument("name")
    pb.set_defaults(func=cmd_brief)

    pp = sub.add_parser("paths", help="Print resolved briefs / DB paths")
    pp.set_defaults(func=cmd_paths)

    pq = sub.add_parser("pending", help="List unread action/urgent messages awaiting your approval")
    pq.set_defaults(func=cmd_pending)

    pe = sub.add_parser("reply", help="Reply to a message")
    pe.add_argument("id", help="Message ID to reply to")
    pe.add_argument("body", help="Reply body, or '-' to read from stdin")
    pe.add_argument("--from", dest="from_", help="Sender (default: operator)")
    pe.add_argument("--priority", default="info", choices=["info", "action", "urgent"])
    pe.set_defaults(func=cmd_reply)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

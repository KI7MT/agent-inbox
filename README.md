# agent-inbox

A single-host message inbox for coordinating multiple AI coding agents
running on the same machine. Works with **any MCP-capable client** —
Claude Code (CLI and Desktop), OpenAI Codex (CLI and desktop app), Cursor,
Cline, Continue, Zed AI, and anything else that speaks the
[Model Context Protocol](https://modelcontextprotocol.io/).

- **MCP server** (Python, FastMCP) — eight tools: `inbox_check`,
  `inbox_read`, `inbox_send`, `inbox_mark`, `inbox_search`, `inbox_agents`,
  `inbox_brief`, `inbox_wait`.
- **Operator CLI** — `agent-inbox` command for the human user. List, read,
  send, approve, reject, watch, manage briefs.
- **Storage** — a single SQLite file. No database server, no daemon,
  no network.
- **Roster** — agents are registered by dropping a markdown brief file
  into the briefs directory. Adding a brief enables a new sender/recipient.
- **Polling** — `inbox_wait` lets agents block on new mail without the
  operator prompting them. Works in any MCP client.
- **Approval gate** — `info` messages act immediately; `action` and
  `urgent` start in `unread` and require the operator to approve. Set
  `AGENT_INBOX_AUTO_APPROVE=1` to skip the gate for solo workflows.

This is a public, single-operator port of an internal multi-host
implementation. Cross-host inboxes are a different problem (auth,
transport, replication) — fork it and put a real database behind it.

## Install

`uv` is the recommended way to manage Python for this project. Install
once if you don't already have it:

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Then clone the repo into your workspace:

```bash
git clone https://github.com/KI7MT/agent-inbox.git
cd agent-inbox
```

That's it — `uv` will sync the venv from `pyproject.toml` automatically
on first run. No manual `venv` step required.

## Wiring it up

MCP clients invoke the server over stdio. **All clients require an
absolute path** in the `command` field — they do not expand `~` or
environment variables. Find the absolute path with:

```bash
# macOS / Linux
realpath bin/agent-inbox-mcp
# Windows (PowerShell)
(Resolve-Path bin\agent-inbox-mcp.cmd).Path
```

Paste that path into your client's MCP config.

### Recommended: `uv run` (truly OS-agnostic, no launcher script)

Works identically on macOS Intel, macOS Silicon, Linux, and Windows.
`uv` must be on the client's PATH.

**Claude Code** (`~/.claude.json`):

```json
{
  "mcpServers": {
    "inbox": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory", "/abs/path/to/agent-inbox",
        "python", "-m", "agent_inbox"
      ]
    }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.inbox]
command = "uv"
args = [
  "run",
  "--directory", "/abs/path/to/agent-inbox",
  "python", "-m", "agent_inbox"
]
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "inbox": {
      "command": "uv",
      "args": [
        "run",
        "--directory", "/abs/path/to/agent-inbox",
        "python", "-m", "agent_inbox"
      ]
    }
  }
}
```

> **macOS GUI app gotcha:** Claude Desktop and Codex desktop app launch
> with a sparse `PATH` that may not include `uv`. If the desktop client
> says "command not found", use the launcher-script form below — it
> resolves `uv` from inside the script after the right shells are sourced.

### Launcher-script form (fallback)

Use these if the client can't find `uv` on its PATH. Both internally
probe for `uv` first and fall back to a `.venv` if present.

**macOS / Linux** — `bin/agent-inbox-mcp`:

```json
{
  "command": "/abs/path/to/agent-inbox/bin/agent-inbox-mcp",
  "args": []
}
```

**Windows** — `bin\agent-inbox-mcp.cmd`:

```json
{
  "command": "C:\\abs\\path\\to\\agent-inbox\\bin\\agent-inbox-mcp.cmd",
  "args": []
}
```

## Quick start

1. Copy the example briefs into your briefs directory:

   ```bash
   bin/agent-inbox paths   # show where briefs go on this OS
   # then:
   mkdir -p "<briefs_dir>"
   cp examples/briefs/*.md "<briefs_dir>/"
   ```

2. Wire the MCP server into your client (see snippets above).

3. From any agent session, call `inbox_agents` to see who's registered,
   `inbox_send` to write a message, `inbox_check` to read your own,
   `inbox_wait` to block until new mail arrives.

4. As the operator, manage the inbox from the terminal:

   ```bash
   bin/agent-inbox list                     # recent messages
   bin/agent-inbox list --for operator      # pending mail for you
   bin/agent-inbox read <id>                # full message
   bin/agent-inbox approve <id>             # approve action/urgent
   bin/agent-inbox reject <id>
   bin/agent-inbox watch --for operator     # live tail
   bin/agent-inbox send --to architect "subject" "body"
   ```

## MCP tools

| Tool            | Purpose                                                      |
| --------------- | ------------------------------------------------------------ |
| `inbox_agents`  | List registered agents and the briefs directory path         |
| `inbox_brief`   | Read another agent's brief (their role and conventions)      |
| `inbox_check`   | Show unread + approved messages for a recipient              |
| `inbox_read`    | Fetch a message by ID                                        |
| `inbox_send`    | Send a message — sender, recipient, priority, subject, body  |
| `inbox_mark`    | Set status to `read`, `in_progress`, or `done`               |
| `inbox_search`  | Filter by sender / recipient / subject substring + lookback  |
| `inbox_wait`    | Block until new mail arrives or timeout (long-poll)          |

## Status flow

```
  unread ──► read ──► in_progress ──► done
     │
     └──► approved ──► in_progress ──► done
     │
     └──► rejected
```

`approved` and `rejected` are reserved for the human operator — set them
via `agent-inbox approve <id>` / `reject <id>`. `AGENT_INBOX_AUTO_APPROVE=1`
makes new `action`/`urgent` messages start as `approved` automatically —
use this if you're the only human in the loop and don't want a manual gate.

## Configuration

| Env var                    | Default (varies by OS)                       | Purpose                                  |
| -------------------------- | -------------------------------------------- | ---------------------------------------- |
| `AGENT_INBOX_BRIEFS`       | OS user-config dir + `/agent-inbox/briefs/`  | Directory of agent brief files           |
| `AGENT_INBOX_DB`           | OS user-data dir + `/agent-inbox/inbox.db`   | SQLite file path                         |
| `AGENT_INBOX_OPERATOR`     | `operator`                                   | Canonical name for the human user        |
| `AGENT_INBOX_AUTO_APPROVE` | unset                                        | Set to `1` to auto-approve action/urgent |

OS-specific defaults (resolved by `platformdirs`):

| OS      | Briefs                                              | DB                                                    |
| ------- | --------------------------------------------------- | ----------------------------------------------------- |
| Linux   | `~/.config/agent-inbox/briefs/`                     | `~/.local/share/agent-inbox/inbox.db`                 |
| macOS   | `~/Library/Application Support/agent-inbox/briefs/` | `~/Library/Application Support/agent-inbox/inbox.db`  |
| Windows | `%APPDATA%\agent-inbox\briefs\`                     | `%LOCALAPPDATA%\agent-inbox\inbox.db`                 |

Run `bin/agent-inbox paths` to see the resolved values on your machine.

## Brief file format

A brief is plain markdown. The filename (without `.md`) is the canonical
agent name. Names must match `^[a-z][a-z0-9_-]*$`. The reserved name `all`
is used for broadcast and cannot be a brief filename.

The contents are advisory — they describe the agent so other agents (or
you) know what role it plays. Other agents can fetch a brief via
`inbox_brief(name)` before deciding to contact it.

`examples/briefs/` ships a reference six-agent set covering a typical
engineering workflow: `operator`, `architect`, `implementer`, `reviewer`,
`tester`, `ops`.

## Polling — how agents stay reactive without prompting

MCP servers can't push, so the agent has to ask. Three patterns, in order
of preference:

1. **`inbox_wait` long-poll** (universal). Brief instructs: "when idle,
   call `inbox_wait` for your name." The tool blocks server-side until
   mail arrives or the timeout elapses (default 30s). Re-call in a loop
   to keep polling. Works in every MCP client.

2. **Client hooks** (per-client, optional). For clients that support
   hooks (Claude Code CLI's `SessionStart`/`Stop`), a hook script can
   call `bin/agent-inbox list --for <name>` and inject the result. Hook
   bundles ship in a future release.

3. **`inbox_check` on demand**. Always works as a manual trigger.

## Development

```bash
git clone https://github.com/KI7MT/agent-inbox.git
cd agent-inbox
uv sync --all-extras
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE).

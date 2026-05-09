# agent-inbox

A single-host message inbox for coordinating multiple AI coding agents
running on the same machine. Works with **any MCP-capable client** — Claude
Code, OpenAI Codex CLI, Cursor, Cline, Continue, Zed AI, and anything else
that speaks the [Model Context Protocol](https://modelcontextprotocol.io/).

- **MCP server** (Python, FastMCP) — six tools: `inbox_check`, `inbox_read`,
  `inbox_send`, `inbox_mark`, `inbox_search`, `inbox_agents`.
- **Storage** — a single SQLite file in `~/.local/share/agent-inbox/inbox.db`.
  No database server, no daemon, no network.
- **Roster** — agents are registered by dropping a markdown brief file into
  the briefs directory (default `~/.config/agent-inbox/briefs/`). Adding a
  brief enables a new sender/recipient. Removing one disables it.
- **Approval gate** (optional) — `info` messages are act-on-immediately;
  `action` and `urgent` start in `unread` and require a human to flip them
  to `approved`. Set `AGENT_INBOX_AUTO_APPROVE=1` to skip the gate for
  single-user setups.

The protocol is vendor-neutral — once the server is running, any number of
agents from any combination of vendors can read and write the same inbox.
A Claude Code session and a Codex CLI session running side-by-side on the
same laptop can hand work to each other through it.

## Install

```bash
pip install agent-inbox-mcp
```

Or in a uv-managed project:

```bash
uv add agent-inbox-mcp
```

The installed entry point is `agent-inbox-mcp` — that's the command MCP
clients spawn over stdio.

## Quick start

1. **Create at least one brief** so the inbox knows who can talk:

   ```bash
   mkdir -p ~/.config/agent-inbox/briefs
   cp examples/briefs/reviewer.md ~/.config/agent-inbox/briefs/
   cp examples/briefs/architect.md ~/.config/agent-inbox/briefs/
   ```

2. **Wire the MCP server into your client** (see per-client snippets below).

3. **From any agent session**, call `inbox_agents` to see who's registered,
   `inbox_send` to write a message, and `inbox_check` to read your own.

## Wiring it up

### Claude Code (`~/.claude.json`)

```json
{
  "mcpServers": {
    "inbox": {
      "type": "stdio",
      "command": "agent-inbox-mcp",
      "args": [],
      "env": {}
    }
  }
}
```

### Codex CLI (`~/.codex/config.toml`)

```toml
[mcp_servers.inbox]
command = "agent-inbox-mcp"
args = []
```

### Generic stdio MCP client

The server reads MCP JSON-RPC on stdin and writes responses on stdout.
Any client that supports stdio MCP servers will work — point it at the
`agent-inbox-mcp` executable with no arguments.

## Tools

| Tool            | Purpose                                                      |
| --------------- | ------------------------------------------------------------ |
| `inbox_agents`  | List registered agents and the briefs directory path         |
| `inbox_check`   | Show unread + approved messages for a recipient              |
| `inbox_read`    | Fetch a message by ID                                        |
| `inbox_send`    | Send a message — sender, recipient, priority, subject, body  |
| `inbox_mark`    | Set status to `read`, `in_progress`, or `done`               |
| `inbox_search`  | Filter by sender / recipient / subject substring + lookback  |

## Status flow

```
  unread ──► read ──► in_progress ──► done
     │
     └──► approved ──► in_progress ──► done
     │
     └──► rejected
```

`approved` and `rejected` are reserved for the human reviewer (set them via
your own UI or by editing the SQLite directly). `AGENT_INBOX_AUTO_APPROVE=1`
makes new `action` / `urgent` messages start as `approved` automatically —
use this if you're the only human in the loop.

## Configuration

| Env var                    | Default                                | Purpose                                  |
| -------------------------- | -------------------------------------- | ---------------------------------------- |
| `AGENT_INBOX_BRIEFS`       | `~/.config/agent-inbox/briefs/`        | Directory of agent brief files           |
| `AGENT_INBOX_DB`           | `~/.local/share/agent-inbox/inbox.db`  | SQLite file path                         |
| `AGENT_INBOX_AUTO_APPROVE` | unset                                  | Set to `1` to auto-approve action/urgent |

XDG environment variables (`XDG_CONFIG_HOME`, `XDG_DATA_HOME`) are honored
when the explicit env vars above are unset.

## Brief file format

A brief is plain markdown. The filename (without `.md`) is the canonical
agent name. Names must match `^[a-z][a-z0-9_-]*$`. The reserved name `all`
is used for broadcast and cannot be a brief filename.

The contents of the file are advisory — they describe the agent so other
agents (or you) know what role it plays. The inbox does not parse them.

Example:

```markdown
# Reviewer

A code-review agent. Reads diffs, looks for security issues, missing tests,
and inconsistencies with the project's conventions.
```

Save that as `~/.config/agent-inbox/briefs/reviewer.md` and `reviewer` is
now a valid sender and recipient.

## Why a single host?

Cross-machine inboxes are a different problem (auth, transport, replication,
ordering). This server stays on one host on purpose — the use case is
multiple agent sessions on a developer's laptop or workstation, not a
distributed system. If you need multi-host, fork it and put a real database
behind it.

## Development

```bash
git clone https://github.com/KI7MT/agent-inbox.git
cd agent-inbox
uv venv
uv pip install -e ".[dev]"
pytest
```

## License

MIT — see [LICENSE](LICENSE).

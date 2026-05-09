# Example Agent Briefs

Six illustrative briefs covering a typical engineering split:

| Brief            | Role                                   |
| ---------------- | -------------------------------------- |
| `operator.md`    | The human user (you)                   |
| `architect.md`   | Systems design and tradeoffs           |
| `implementer.md` | Writes the code                        |
| `reviewer.md`    | Code review, security, conventions     |
| `tester.md`      | Test planning and failure analysis     |
| `ops.md`         | Deploys, CI/CD, infrastructure         |

The filename (without `.md`) is the agent's canonical name. Names must match
`^[a-z][a-z0-9_-]*$`. The reserved name `all` is used for broadcast and must
not be a brief filename.

## Wiring up the operator brief

The operator name defaults to `operator`. If you want to use a different
name (your initials, your team handle, etc.), set `AGENT_INBOX_OPERATOR`
and rename `operator.md` to match:

```bash
export AGENT_INBOX_OPERATOR=alice
cp operator.md alice.md
```

## Installing into your runtime briefs directory

Print where the inbox is looking, then copy:

```bash
agent-inbox paths
# briefs_dir: /Users/alice/Library/Application Support/agent-inbox/briefs
# db_path:    /Users/alice/Library/Application Support/agent-inbox/inbox.db

mkdir -p "$(agent-inbox paths | awk '/briefs_dir/{print $2}')"
cp examples/briefs/*.md "$(agent-inbox paths | awk '/briefs_dir/{print $2}')/"
```

The MCP server picks up changes on every tool call — no restart needed.

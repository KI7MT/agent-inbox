# Example Agent Briefs

These are illustrative briefs you can copy into your real briefs directory
(default `~/.config/agent-inbox/briefs/`) to register agents.

The filename (without `.md`) is the agent's canonical name. The reserved
name `all` is used for broadcast and must not be a brief filename. Names
must match `^[a-z][a-z0-9_-]*$`.

To start fresh:

```bash
mkdir -p ~/.config/agent-inbox/briefs
cp examples/briefs/reviewer.md ~/.config/agent-inbox/briefs/
cp examples/briefs/architect.md ~/.config/agent-inbox/briefs/
```

The MCP server picks up changes on every tool call — no restart needed.

# Example Agent Briefs

Seven illustrative briefs covering a typical engineering workflow.
Each is a self-contained markdown file describing one role: what the
agent does, what it refuses to do, what it consumes, what it
produces, and where it sits in the pipeline. Drop them into your
briefs directory (default `~/.config/agent-inbox/briefs/`) and they
become valid `sender` / `recipient` names immediately.

The bundle is intended as a starting point, not a prescription —
operators are expected to edit, rename, drop, or replace any of these
to match how their team actually works.

## The seven roles

| Brief                  | Role                                              |
| ---------------------- | ------------------------------------------------- |
| `operator.md`          | The human user (you) — drives, decides, approves  |
| `architect.md`         | Systems design and tradeoff documentation         |
| `implementer.md`       | Writes the code from a design or spec             |
| `reviewer.md`          | Code review for security, conventions, gaps      |
| `failure-analyst.md`   | Adversarial probes, parity checks, falsification  |
| `tester.md`            | Test plans, fixtures, failure reproduction        |
| `ops.md`               | CI/CD, infrastructure, runtime environment       |

## Typical pipeline

A change moves through these roles in roughly this order. Not every
change touches every role — small bug fixes might skip architect; a
deploy-only change is mostly between ops and operator.

```
                          ┌──── feedback ─────┐
                          ▼                   │
   operator ──► architect ──► implementer ──► reviewer
                                  │              │
                                  │              ▼
                                  │         failure-analyst
                                  │              │
                                  ▼              ▼
                                tester ◄──────────┘
                                  │
                                  ▼
                                 ops ──► operator (release call)
```

The operator sits at both ends — kicking off the work with scope and
constraints, and accepting (or rejecting) the output for release.
Every other agent pings the operator only when their brief says they
should: a tradeoff that needs a human call, a security finding above
their lane, a question that depends on context only the operator
holds.

## Voice and disposition

The briefs are written in a uniform voice on purpose — plain,
declarative, no marketing. Each opens with one paragraph saying what
the agent does and how it approaches the work, then breaks into
sections:

- **Strengths** — concrete capabilities, not adjectives
- **Avoids** — what the agent declines, even when asked
- **Inputs** — what to send, in what format
- **Outputs** — what to expect back, in what shape
- **Hand-offs** — who receives the agent's output and what they need
- **When to use** — right time vs wrong time to invoke the agent

Operators forking the bundle are encouraged to keep this skeleton —
the consistency makes briefs scannable across roles. Voice and tone
are personal preference; don't sweat that.

## Wiring up the operator brief

The operator name defaults to `operator`. To use a different name
(your initials, your team handle, etc.), set `AGENT_INBOX_OPERATOR`
and rename `operator.md` to match:

```bash
export AGENT_INBOX_OPERATOR=alice
mv operator.md alice.md
```

Names must match `^[a-z][a-z0-9_-]*$`. Reserved names: `all`
(broadcast). Trailing whitespace and newlines are rejected.

## Installing into your runtime briefs directory

Print where the inbox is looking, then copy:

```bash
agent-inbox paths
# briefs_dir: /Users/alice/Library/Application Support/agent-inbox/briefs
# db_path:    /Users/alice/Library/Application Support/agent-inbox/inbox.db

mkdir -p "$(agent-inbox paths | awk '/briefs_dir/{print $2}')"
cp examples/briefs/*.md "$(agent-inbox paths | awk '/briefs_dir/{print $2}')/"
```

The MCP server picks up brief changes on every tool call — no restart
needed. Drop a new file in, the new agent is registered. Remove a
file, the agent is gone (and any unread mail addressed to them is no
longer reachable, so prefer renaming over deletion if there's mail in
flight).

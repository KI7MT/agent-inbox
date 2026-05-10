# Operator

The human in the loop. Drives the work, makes final calls on
architecture and scope, owns the relationships with external
services, and approves any `action` or `urgent` messages between
agents before those messages can be acted on. Disposition is
decisive — operator's job is to make calls the agents can't make
alone and to make them quickly enough that the agents stay
productive.

Other agents send to `operator` when they need a decision, want to
surface a tradeoff, or have hit a question that's outside their
lane. Operator responds with the call (and the reason), or with a
question back to narrow the choice.

## Strengths

- Holding the actual problem the project is solving — agents work
  feature by feature; operator remembers what success looks like
- Owning external relationships: the customers, the budget, the
  legal calls, the API keys, the SaaS choices, the timing
- Calibrating risk against ambition — operator decides when "good
  enough" is genuinely enough and when it's not
- Reading agent output for what it is — useful but not infallible
  — and asking sharper questions when output is too smooth to be
  trustworthy
- Knowing the system end to end well enough to call out when an
  agent's work doesn't fit, even if each individual piece is good

## Avoids

- Doing agent work — operator who steps into implementer's lane
  ends up with a worse result and a confused implementer next time
- Approving `action` and `urgent` messages on autopilot; the
  approval gate exists because some of those messages should be
  rejected, and rubber-stamping them defeats the model
- Letting agent decisions slip past without a clear answer —
  silence reads as approval to the agent and as ambiguity to the
  human reviewing the result later
- Making promises to external parties that the agents can't
  actually deliver in the time available
- Bikeshedding on agent output — if it works, ship it; comments
  belong on the PR, not in a string of inbox messages

## Inputs

- An agent's `action` or `urgent` message asking for a decision,
  a tradeoff call, or surfaced ambiguity in the brief
- A status ping at the end of a long-running task ("done, 159
  tests pass, here's the tag")
- An escalation from any agent that crosses a line the operator
  drew (cost, vendor commitments, scope, security)
- A question whose answer requires context only the operator has
  (customer needs, budget constraints, calendar)

## Outputs

- A decision (yes / no / refined ask), with enough rationale that
  the agent can apply it to similar future cases without re-asking
- A pointer to documentation, a prior decision, or another agent's
  brief when the answer is "you can answer this yourself"
- A status update the agents can act on: "go ahead", "hold", "pull
  in X first", "this is on hold until Y resolves"
- An explicit `approved` or `rejected` flip on `action` / `urgent`
  messages via the inbox UI or `agent-inbox approve <id>` /
  `agent-inbox reject <id>`

## Hand-offs

- **To architect**: when a question crosses the design / scope
  boundary the operator owns. Architect handles "how"; operator
  handles "whether" and "what for".
- **To implementer**: clear specs, explicit acceptance criteria,
  and an explicit "go" — implementer needs the spec and the green
  light, in that order.
- **To reviewer / failure-analyst**: trust their findings; if you
  disagree, reply with the reason, don't override silently.
- **To ops**: own the credential / vendor / cost calls. Ops
  refuses to make them; that's correct, and it's why operator
  exists.
- **To other operators (rare)**: in real teams there's only one
  operator at a time on a given decision; multi-operator
  workflows get confused fast unless the boundaries are clear.

## When to use

Right time: any moment an agent surfaces an `action` or `urgent`
message; at the start of a feature to set scope; at the end of a
release to call ship / no-ship; whenever an agent asks a question
that depends on context outside the codebase.

Wrong time: during routine intra-agent coordination — agents
passing diffs and findings between themselves shouldn't go
through the operator. That's noise; the inbox approval gate is
for `action` and `urgent`, not `info`. Pulling routine `info`
traffic up to the operator drowns the signal that needs the
operator's attention.

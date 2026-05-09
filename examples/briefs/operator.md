# Operator

The human in the loop. Drives the work, makes final calls on architecture
and scope, and approves any `action` or `urgent` messages between agents.

Other agents send to `operator` when they need a decision, want to surface
a tradeoff, or have hit a question that's outside their lane.

## What to send the operator
- Yes/no decisions you can't resolve from your brief
- Tradeoffs with two reasonable answers
- Anything that touches money, infrastructure costs, or external services
- Status pings at the end of long-running tasks

## What not to send
- Routine coordination between agents (use `inbox_send` directly to the peer)
- Acknowledgements (use `inbox_mark` to flip status to `done`)
- Anything you can answer yourself by reading another agent's brief

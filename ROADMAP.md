# Roadmap

What's likely, what's maybe, what's explicitly out of scope. Not dated —
this isn't a product plan, it's a thinking document for whoever's
deciding what to do next.

## Done (recent)

| Tag | What |
|---|---|
| v0.3.x audit cycle | Four rounds of failure-analysis review (Patton) + voice review (Watson). All findings landed. |
| v0.3.7 — v0.3.11 | Tier-1 CI → multi-OS / multi-Python matrix → lint job → Wails GUI build smoke → action version polish. Twelve-cell CI on every push and PR, branch protection ruleset gating `ci-all-green`. |
| v0.4.0 | Example briefs expanded from sketches to full role definitions. New `failure-analyst.md` slot. `examples/README.md` rewritten with the seven-role pipeline diagram. |

## Likely (v0.4.x)

Small, low-risk hygiene items. Doable in single PRs, no design pass needed.

- **Dependabot config** — auto-open PRs for GitHub Actions and Python
  dependency version bumps. Catches the kind of drift that surfaced
  the setup-uv / golangci-lint Node 20 chase manually. ~10 lines of
  YAML in `.github/dependabot.yml`.
- **CodeQL workflow** — GitHub-side static analysis, free for public
  repos. One-click enable from the Security tab; minimal workflow file.
  Surfaces the kind of issue ruff and golangci-lint don't catch.
- **Coverage upload** — codecov or coveralls. Less essential now that
  the test matrix has multi-OS + multi-Python coverage validated, but
  cheap to add and produces a status badge.
- **Issue triage labels** — beyond the default set, add `audit` (for
  failure-analyst flags), `parity` (Python ↔ Go drift), `sandbox-blocked`
  (needs hardware we don't have in CI). Keeps backlog scannable.

## Maybe (v0.5.x)

Larger items that need a design or scope decision before starting.

- **Claude Code hooks bundle** — the auto-polling pattern from earlier
  scoping. `SessionStart` and `Stop` hooks that call `inbox_check` and
  inject the result so agents react without the operator prompting.
  Distributed under `examples/hooks/claude-code/`. Ships as opt-in
  config snippets, not enabled by default. Codex CLI hook equivalent
  if their hook system supports it.
- **Slash-command skills pack** — `/inbox-check`, `/inbox-send`,
  `/inbox-list` for Claude Code under `examples/skills/claude-code/`.
  Operator side: terminal-friendly aliases for the actions taken
  most often.
- **`agent-inbox install` CLI subcommand** — automates the brief-bundle
  copy into the OS-specific config dir, plus optionally writes the
  client config snippet (Claude Code / Codex CLI / Claude Desktop).
  Reduces the "type the absolute path correctly" friction Patton
  flagged in earlier review.
- **PyPI publish** — `pip install agent-inbox-mcp`. Needs trusted
  publisher setup on PyPI side, a release workflow that triggers on
  tag push, and the discipline to keep `pyproject.toml` metadata
  accurate. Worth considering if the repo gets external interest.
- **Reply-thread visualization in the UI** — currently flat list with
  a `↳` glyph for `parent_id`. A proper tree view in the detail pane
  would make multi-hop conversations easier to follow. Schema columns
  already in place.
- **Live updates via Wails events** — replace the 2-second JS polling
  with `EventsEmit` / `EventsOn` for instant push from Go to Svelte
  when SQLite changes. Lower CPU at idle, instant feel. Needs a
  filesystem watcher or trigger on writes; not technically hard but
  needs design.

## Out of scope

Calling out the things people might assume the project should do but won't.

- **Cross-host coordination** — the README says single-host on purpose.
  Auth, transport, replication, ordering are different problems with
  different solutions. Forking the repo and putting a real database
  behind it is the right move if that's what's needed; agent-inbox is
  not the foundation for that work.
- **Multi-tenant operation** — the trust model is single-trusted-operator.
  Adding sender authentication, per-message encryption, etc. would
  fundamentally change the design and the audience.
- **Mobile companion app** — already considered (Compose Multiplatform
  briefly entertained, declined). The desktop UI is what's required for
  the core use case; a phone client would be its own project, not a
  fork of this one.
- **General-purpose message queue** — agent-inbox is shaped for
  AI-coding-agent coordination specifically. Using it as a generic
  in-process pub/sub is possible but the API and trust model are
  designed for the narrower case.

## How items move

Items in **Likely** ship without a roadmap update — open a PR, iterate,
merge, tag. Items in **Maybe** get an issue first to capture scope and
constraints before any code work. Items in **Out of scope** stay there
unless someone makes a strong argument otherwise; the default answer is
"that's a different project."

This file is a snapshot of intent, not a contract. PRs are welcome on
items in **Likely** without checking first; for **Maybe** items, an
issue or inbox conversation first saves wasted work.

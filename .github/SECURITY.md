# Security policy

## Reporting a vulnerability

**Please don't open a public issue for security vulnerabilities.** Use
[GitHub Security Advisories](https://github.com/KI7MT/agent-inbox/security/advisories/new)
to report privately. The maintainer will be notified and we'll coordinate
disclosure from there.

What to include:

- A clear description of the issue and its impact
- Steps to reproduce, or a minimal proof-of-concept
- The version (`agent-inbox --version` or git tag) where you observed it
- Your operating system and MCP client, if relevant
- Suggested mitigation, if you have one in mind

Expect an initial response within a few days. If you don't hear back, feel
free to nudge via the same advisory thread.

## Trust model — what is and isn't a vulnerability

agent-inbox is designed for **a single trusted operator on one
workstation**. The README's "Trust model" section spells out what this
means in detail. Some specific implications for security reports:

- **Sender spoofing** — any process that can talk to the MCP server can
  claim any sender name. This is documented and intentional within the
  single-operator scope. It's not a vulnerability.
- **Reading any message by ID** — same: documented behavior. The trust
  boundary is the OS user owning the SQLite file.
- **The operator UI's `Approve`/`Reject` bindings have no caller
  verification** — by design, since the webview is owned by the
  operator's desktop session.

Things that *are* in-scope and worth reporting:

- Anything that lets an unrelated process on the same machine read or
  write the inbox without going through the documented MCP/CLI/UI paths
- Markdown rendering in the desktop UI escaping its sanitizer
  (DOMPurify) and executing script
- SQL injection through any input that reaches the database
- Path traversal allowing the inbox or briefs to be read or written
  outside their configured directories
- Any way a malicious message body can crash, hang, or exhaust the
  resources of the server, CLI, or UI
- Cross-OS parity drift that creates a security difference between the
  Python and Go layers

When in doubt, file the advisory anyway — it's better to discuss a borderline
case privately than to leave it sitting.

## Versions covered

The current `main` branch and the most recent tagged release (currently
`v0.3.5+`) are supported. Older tags are not actively patched; please
upgrade if you can.

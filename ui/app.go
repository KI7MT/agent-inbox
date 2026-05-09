// Wails-bound App struct. These methods are exposed to the Svelte
// frontend via wails generate.

package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"unicode/utf8"
)

// agentSettableStatuses are the statuses agents may assign via SetStatus.
// Operator-only statuses (approved, rejected) go through Approve/Reject.
var agentSettableStatuses = map[string]bool{
	"read":        true,
	"in_progress": true,
	"done":        true,
}

var validPriorities = map[string]bool{
	"info":   true,
	"action": true,
	"urgent": true,
}

// Bounds mirror src/agent_inbox/core.py — character counts in both layers.
// Go's `len(string)` counts bytes; we use utf8.RuneCountInString for parity
// with Python's `len(str)` so a 500-emoji subject is treated identically
// (e.g., 🌪×500 is 500 chars in both, not 500 in Python and 2000 in Go).
const (
	maxSubjectLen       = 500
	maxBodyLen          = 1_000_000
	maxSearchSubjectLen = 1000
)

func validateLengths(subject, body string) error {
	if n := utf8.RuneCountInString(subject); n > maxSubjectLen {
		return fmt.Errorf("subject too long: %d chars (max %d)", n, maxSubjectLen)
	}
	if n := utf8.RuneCountInString(body); n > maxBodyLen {
		return fmt.Errorf("body too long: %d chars (max %d)", n, maxBodyLen)
	}
	return nil
}

// Paths is what GetPaths returns — the resolved locations on this OS.
type Paths struct {
	BriefsDir string `json:"briefs_dir"`
	DBPath    string `json:"db_path"`
	Operator  string `json:"operator"`
}

// AgentInfo is one row in the agent sidebar.
type AgentInfo struct {
	Name        string `json:"name"`
	IsOperator  bool   `json:"is_operator"`
	PendingMail int    `json:"pending_mail"` // unread+approved for this recipient
}

// App is the main application struct exposed to the frontend.
type App struct {
	ctx   context.Context
	store *store
}

// NewApp constructs the App and opens the SQLite store. Fails fast if
// the store can't be opened — better to crash at startup with a clear
// reason than to launch a window where every action returns "store not
// initialized".
func NewApp() (*App, error) {
	st, err := newStore(dbPath())
	if err != nil {
		return nil, fmt.Errorf("open inbox store at %s: %w", dbPath(), err)
	}
	return &App{store: st}, nil
}

func (a *App) startup(ctx context.Context) {
	a.ctx = ctx
}

// Shutdown is called by Wails when the window is closed.
func (a *App) Shutdown(ctx context.Context) {
	if a.store != nil {
		_ = a.store.close()
	}
}

// Ping is a health check. Returns "ok" on success.
func (a *App) Ping() (string, error) {
	if a.store == nil {
		return "", errors.New("store not initialized")
	}
	if err := a.store.ensureSchema(); err != nil {
		return "", err
	}
	return "ok", nil
}

// GetPaths returns the resolved briefs / DB / operator paths.
func (a *App) GetPaths() Paths {
	return Paths{
		BriefsDir: briefsDir(),
		DBPath:    dbPath(),
		Operator:  operatorName(),
	}
}

// GetAgents returns the registered agents plus per-agent attention counts
// for the sidebar.
func (a *App) GetAgents() ([]AgentInfo, error) {
	names := loadAgents()
	if a.store == nil {
		return nil, errors.New("store not initialized")
	}
	st, err := a.store.stats()
	if err != nil {
		return nil, err
	}
	op := operatorName()
	out := make([]AgentInfo, 0, len(names))
	for _, n := range names {
		out = append(out, AgentInfo{
			Name:        n,
			IsOperator:  n == op,
			PendingMail: st.ByRecipient[n] + st.ByRecipient["all"],
		})
	}
	return out, nil
}

// GetBrief returns the markdown contents of an agent's brief, or an empty
// string if none exists.
func (a *App) GetBrief(name string) string {
	return readBrief(strings.ToLower(name))
}

// GetMessages is the generic list endpoint.
//
//   view — one of: "all", "pending_approval", "for_recipient", "search"
//   recipient — for "for_recipient" view, the agent name
//   sender / subject / days / limit — for "search" view
//
// Returning empty slices (not nil) keeps the JS side from having to
// guard for null.
func (a *App) GetMessages(
	view, recipient, sender, subject string,
	days, limit int,
) ([]Message, error) {
	if a.store == nil {
		return nil, errors.New("store not initialized")
	}
	switch view {
	case "pending_approval", "pending":
		return a.store.listPendingApproval()
	case "for_recipient":
		if recipient == "" {
			return nil, errors.New("recipient required for for_recipient view")
		}
		return a.store.listForRecipient(strings.ToLower(recipient))
	case "search":
		if n := utf8.RuneCountInString(subject); n > maxSearchSubjectLen {
			return nil, fmt.Errorf(
				"search subject too long: %d chars (max %d)",
				n, maxSearchSubjectLen,
			)
		}
		return a.store.search(strings.ToLower(sender), strings.ToLower(recipient), subject, days, limit)
	case "all", "":
		if limit <= 0 {
			limit = 200
		}
		return a.store.listRecent(limit)
	default:
		return nil, fmt.Errorf("unknown view: %q", view)
	}
}

// GetMessage fetches one message by id.
func (a *App) GetMessage(id string) (Message, error) {
	if a.store == nil {
		return Message{}, errors.New("store not initialized")
	}
	m, err := a.store.getMessage(id)
	return m, translateNotFound(err)
}

// SendResult is what SendMessage returns. For direct sends, IDs has one
// element. For broadcasts (to == "all"), IDs has one entry per recipient
// (the broadcast is fanned out at send time so each recipient has their
// own row and their own status — no shared global state).
type SendResult struct {
	From         string   `json:"from"`
	To           string   `json:"to"`
	Priority     string   `json:"priority"`
	Subject      string   `json:"subject"`
	IDs          []string `json:"ids"`
	BroadcastTo  []string `json:"broadcast_to,omitempty"`
}

// SendMessage sends a new message. Broadcasts (to == "all") fan out into
// one independent message per registered agent (excluding the sender).
func (a *App) SendMessage(from, to, priority, subject, body string) (SendResult, error) {
	if a.store == nil {
		return SendResult{}, errors.New("store not initialized")
	}
	from = strings.ToLower(from)
	to = strings.ToLower(to)
	priority = strings.ToLower(priority)
	if !validPriorities[priority] {
		return SendResult{}, fmt.Errorf("invalid priority: %q (must be info/action/urgent)", priority)
	}
	if err := validateAgent(from, true /* allowOperator */, false /* allowBroadcast */); err != nil {
		return SendResult{}, err
	}
	if err := validateAgent(to, true, true); err != nil {
		return SendResult{}, err
	}
	if err := validateLengths(subject, body); err != nil {
		return SendResult{}, err
	}

	op := operatorName()

	if to == "all" {
		var targets []string
		for _, n := range loadAgents() {
			if n != from {
				targets = append(targets, n)
			}
		}
		if len(targets) == 0 {
			return SendResult{
				From: from, To: to, Priority: priority, Subject: subject,
				BroadcastTo: nil, IDs: nil,
			}, nil
		}
		var delivered []string
		ids := make([]string, 0, len(targets))
		for _, target := range targets {
			// Orphan guard: target's brief might have been unlinked
			// between snapshot and now. Skip rather than write an
			// unreachable row. Mirrors src/agent_inbox/core.py:send.
			current := loadAgents()
			stillRegistered := target == op
			for _, n := range current {
				if n == target {
					stillRegistered = true
					break
				}
			}
			if !stillRegistered {
				continue
			}
			id, err := a.store.insertMessage(from, target, priority, subject, body, nil)
			if err != nil {
				return SendResult{}, err
			}
			ids = append(ids, id)
			delivered = append(delivered, target)
		}
		return SendResult{
			From: from, To: to, Priority: priority, Subject: subject,
			BroadcastTo: delivered, IDs: ids,
		}, nil
	}

	// Direct-send orphan guard: recipient's brief might have been removed
	// between validation and now. Hard-error rather than write a row the
	// recipient could never `inbox_check`.
	if err := validateAgent(to, true /* allowOperator */, false /* allowBroadcast */); err != nil {
		return SendResult{}, fmt.Errorf(
			"cannot send: recipient %q is no longer in the brief registry: %w",
			to, err,
		)
	}
	id, err := a.store.insertMessage(from, to, priority, subject, body, nil)
	if err != nil {
		return SendResult{}, err
	}
	return SendResult{
		From: from, To: to, Priority: priority, Subject: subject,
		IDs: []string{id},
	}, nil
}

// ReplyMessage replies to a message. The reply goes back to the original
// sender; the subject is auto-prefixed with "Re: " unless already prefixed.
// `from` must have been the original recipient or the original must be a
// broadcast.
func (a *App) ReplyMessage(from, inReplyTo, body, priority string) (string, error) {
	if a.store == nil {
		return "", errors.New("store not initialized")
	}
	from = strings.ToLower(from)
	priority = strings.ToLower(priority)
	if priority == "" {
		priority = "info"
	}
	if !validPriorities[priority] {
		return "", fmt.Errorf("invalid priority: %q", priority)
	}
	if err := validateAgent(from, true, false); err != nil {
		return "", err
	}
	if err := validateLengths("", body); err != nil {
		return "", err
	}
	parent, err := a.store.getMessage(inReplyTo)
	if err != nil {
		return "", translateNotFound(err)
	}
	if parent.Recipient != from && parent.Recipient != "all" {
		return "", fmt.Errorf(
			"cannot reply: %q was not the recipient of message %s (sent to %q)",
			from, inReplyTo, parent.Recipient,
		)
	}
	dest := strings.ToLower(parent.Sender)
	// Orphan-recipient guard: if the original sender's brief was removed
	// since the parent was sent, the reply would land somewhere the
	// registry no longer knows about. Hard-error rather than create an
	// invisible row.
	if err := validateAgent(dest, true /* allowOperator */, false /* allowBroadcast */); err != nil {
		return "", fmt.Errorf(
			"cannot reply: original sender %q is no longer in the brief registry: %w",
			dest, err,
		)
	}
	subject := parent.Subject
	if !strings.HasPrefix(strings.ToLower(subject), "re:") {
		subject = "Re: " + subject
	}
	// Re-check length after the "Re: " prefix is added — same reason as
	// the Python side.
	if err := validateLengths(subject, body); err != nil {
		return "", err
	}
	return a.store.insertMessage(from, dest, priority, subject, body, &parent.ID)
}

// SetStatus assigns an agent-settable status to a message.
func (a *App) SetStatus(id, status string) error {
	if a.store == nil {
		return errors.New("store not initialized")
	}
	status = strings.ToLower(status)
	if !agentSettableStatuses[status] {
		return fmt.Errorf("status %q is not agent-settable (use Approve/Reject)", status)
	}
	return translateNotFound(a.store.updateStatus(id, status))
}

// Approve flips a message to status="approved" — operator action.
func (a *App) Approve(id string) error {
	if a.store == nil {
		return errors.New("store not initialized")
	}
	return translateNotFound(a.store.updateStatus(id, "approved"))
}

// Reject flips a message to status="rejected" — operator action.
func (a *App) Reject(id string) error {
	if a.store == nil {
		return errors.New("store not initialized")
	}
	return translateNotFound(a.store.updateStatus(id, "rejected"))
}

// GetStats returns the counts shown in the StatsBar.
func (a *App) GetStats() (Stats, error) {
	if a.store == nil {
		return Stats{}, errors.New("store not initialized")
	}
	return a.store.stats()
}

// validateAgent enforces that `name` is in the brief-derived registry.
//
//   allowOperator: include the operator name (always implicitly registered)
//   allowBroadcast: also accept "all"
func validateAgent(name string, allowOperator, allowBroadcast bool) error {
	if allowBroadcast && name == "all" {
		return nil
	}
	if allowOperator && name == operatorName() {
		// The operator is always implicitly registered, even if there's
		// no brief file. (There usually IS one, but don't make absence
		// fatal.)
		return nil
	}
	for _, n := range loadAgents() {
		if n == name {
			return nil
		}
	}
	return fmt.Errorf("invalid agent: %q (no brief in %s)", name, briefsDir())
}

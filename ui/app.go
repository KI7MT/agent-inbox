// Wails-bound App struct. These methods are exposed to the Svelte
// frontend via wails generate.

package main

import (
	"context"
	"errors"
	"fmt"
	"strings"
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

// NewApp constructs the App and opens the SQLite store. If the store
// can't be opened (rare — bad path, permissions), the methods will
// return errors when called.
func NewApp() *App {
	st, err := newStore(dbPath())
	if err != nil {
		fmt.Fprintln(stderrWriter(), "agent-inbox-ui:", err)
	}
	return &App{store: st}
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

// SendMessage sends a new message. The `from` argument lets the operator
// or a script send as a specific agent (the UI passes operatorName() by
// default for outgoing operator messages).
func (a *App) SendMessage(from, to, priority, subject, body string) (string, error) {
	if a.store == nil {
		return "", errors.New("store not initialized")
	}
	from = strings.ToLower(from)
	to = strings.ToLower(to)
	priority = strings.ToLower(priority)
	if !validPriorities[priority] {
		return "", fmt.Errorf("invalid priority: %q (must be info/action/urgent)", priority)
	}
	if err := validateAgent(from, true /* allowOperator */, false /* allowBroadcast */); err != nil {
		return "", err
	}
	if err := validateAgent(to, true, true); err != nil {
		return "", err
	}
	return a.store.insertMessage(from, to, priority, subject, body, nil)
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
	subject := parent.Subject
	if !strings.HasPrefix(strings.ToLower(subject), "re:") {
		subject = "Re: " + subject
	}
	return a.store.insertMessage(from, parent.Sender, priority, subject, body, &parent.ID)
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

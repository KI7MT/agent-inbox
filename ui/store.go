// SQLite storage layer. Mirrors src/agent_inbox/db.py — same schema,
// same PRAGMA discipline (WAL, busy_timeout=5000, synchronous=NORMAL),
// same retry-on-lock semantics. Both Python and Go layers can read and
// write the same inbox.db safely.
//
// We use modernc.org/sqlite (pure Go) so cross-compilation to macOS,
// Windows, and Linux doesn't need CGO. The Python side is the
// canonical schema author; this Go side picks up whatever the Python
// migration produced.

package main

import (
	"database/sql"
	"errors"
	"fmt"
	"math/rand/v2"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
	_ "modernc.org/sqlite"
)

const (
	busyTimeoutMs       = 5000
	writeRetryMax       = 3
	writeRetryBaseDelay = 25 * time.Millisecond
)

// schemaSQL is identical to SCHEMA in src/agent_inbox/db.py.
const schemaSQL = `
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_unix INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS INTEGER)),
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    priority TEXT NOT NULL CHECK(priority IN ('info','action','urgent')),
    status TEXT NOT NULL DEFAULT 'unread'
        CHECK(status IN ('unread','read','approved','rejected','in_progress','done')),
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    parent_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_recipient_status ON messages(recipient, status);
CREATE INDEX IF NOT EXISTS idx_timestamp ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_created_unix ON messages(created_unix);
CREATE INDEX IF NOT EXISTS idx_parent_id ON messages(parent_id);
`

// store wraps a *sql.DB plus a once-per-process schema-init guard.
type store struct {
	db          *sql.DB
	initOnce    sync.Once
	initErr     error
	autoApprove bool
}

func newStore(path string) (*store, error) {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return nil, fmt.Errorf("create db dir: %w", err)
	}
	// Ordering note: busy_timeout is set first so the journal_mode=WAL
	// switch (which needs an EXCLUSIVE lock) respects it under contention.
	dsn := fmt.Sprintf(
		"file:%s?_pragma=busy_timeout(%d)&_pragma=synchronous(NORMAL)"+
			"&_pragma=foreign_keys(ON)",
		path, busyTimeoutMs,
	)
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, fmt.Errorf("open sqlite: %w", err)
	}
	// Single connection serializes writes within this process; SQLite's
	// own busy_timeout handles the inter-process case.
	db.SetMaxOpenConns(1)
	if err := db.Ping(); err != nil {
		return nil, fmt.Errorf("ping sqlite: %w", err)
	}
	s := &store{
		db:          db,
		autoApprove: os.Getenv("AGENT_INBOX_AUTO_APPROVE") == "1",
	}
	if err := s.ensureWAL(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ensure WAL: %w", err)
	}
	return s, nil
}

// ensureWAL switches the DB to WAL journal mode if it isn't already.
// Sticky cross-process; only the first process touching a fresh DB has
// to take the EXCLUSIVE lock to do the switch, and that can be contested
// by other processes opening simultaneously. The retry covers that case.
func (s *store) ensureWAL() error {
	var mode string
	if err := s.db.QueryRow("PRAGMA journal_mode").Scan(&mode); err != nil {
		return fmt.Errorf("read journal_mode: %w", err)
	}
	if strings.EqualFold(mode, "wal") {
		return nil
	}
	_, err := withRetry(func() (string, error) {
		var got string
		if e := s.db.QueryRow("PRAGMA journal_mode=WAL").Scan(&got); e != nil {
			return got, e
		}
		if !strings.EqualFold(got, "wal") {
			return got, fmt.Errorf("WAL switch did not take effect (got %q, busy)", got)
		}
		return got, nil
	})
	return err
}

// ensureSchema runs CREATE TABLE IF NOT EXISTS once per process. The
// Python side handles ALTER-TABLE migrations; we only make sure the base
// schema exists in case the UI is the first thing to touch the file.
func (s *store) ensureSchema() error {
	s.initOnce.Do(func() {
		if _, err := s.db.Exec(schemaSQL); err != nil {
			s.initErr = fmt.Errorf("init schema: %w", err)
		}
	})
	return s.initErr
}

func (s *store) close() error {
	return s.db.Close()
}

// isLockErr matches the error messages SQLite raises on contention.
func isLockErr(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "locked") || strings.Contains(msg, "busy")
}

// withRetry runs op with exponential backoff on lock errors.
func withRetry[T any](op func() (T, error)) (T, error) {
	var zero T
	var lastErr error
	for attempt := 0; attempt <= writeRetryMax; attempt++ {
		v, err := op()
		if err == nil {
			return v, nil
		}
		if !isLockErr(err) {
			return zero, err
		}
		lastErr = err
		if attempt == writeRetryMax {
			break
		}
		delay := writeRetryBaseDelay * (1 << attempt)
		jitter := time.Duration(rand.Int64N(int64(delay) / 4))
		time.Sleep(delay + jitter)
	}
	return zero, lastErr
}

// Message mirrors the agent_inbox.db row shape.
type Message struct {
	ID          string  `json:"id"`
	Timestamp   string  `json:"timestamp"`
	CreatedUnix int64   `json:"created_unix"`
	Sender      string  `json:"sender"`
	Recipient   string  `json:"recipient"`
	Priority    string  `json:"priority"`
	Status      string  `json:"status"`
	Subject     string  `json:"subject"`
	Body        string  `json:"body"`
	ParentID    *string `json:"parent_id,omitempty"`
}

func scanMessage(row interface {
	Scan(...any) error
}) (Message, error) {
	var m Message
	var parent sql.NullString
	err := row.Scan(
		&m.ID, &m.Timestamp, &m.CreatedUnix, &m.Sender, &m.Recipient,
		&m.Priority, &m.Status, &m.Subject, &m.Body, &parent,
	)
	if err != nil {
		return m, err
	}
	if parent.Valid {
		m.ParentID = &parent.String
	}
	return m, nil
}

const messageColumns = `id, timestamp, created_unix, sender, recipient, priority, status, subject, body, parent_id`

// listForRecipient returns the messages a recipient should act on now.
//
// Approval gate: action/urgent messages stay invisible to the recipient
// until the operator approves them (status flips from 'unread' to
// 'approved'). info messages are act-on-immediately and appear while
// still 'unread'. This mirrors src/agent_inbox/db.py:list_for_recipient.
func (s *store) listForRecipient(recipient string) ([]Message, error) {
	if err := s.ensureSchema(); err != nil {
		return nil, err
	}
	rows, err := s.db.Query(
		`SELECT `+messageColumns+
			` FROM messages
              WHERE recipient IN (?, 'all')
                AND (
                  (status = 'unread' AND priority = 'info')
                  OR status = 'approved'
                )
              ORDER BY created_unix`,
		recipient,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectMessages(rows)
}

// listPendingApproval returns action/urgent messages awaiting operator
// approval, urgent first.
func (s *store) listPendingApproval() ([]Message, error) {
	if err := s.ensureSchema(); err != nil {
		return nil, err
	}
	rows, err := s.db.Query(`
		SELECT ` + messageColumns + `
		FROM messages
		WHERE status = 'unread' AND priority IN ('action', 'urgent')
		ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'action' THEN 1 ELSE 2 END,
		         created_unix
	`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectMessages(rows)
}

// listRecent returns the most recent messages across all agents.
func (s *store) listRecent(limit int) ([]Message, error) {
	if err := s.ensureSchema(); err != nil {
		return nil, err
	}
	if limit <= 0 || limit > 500 {
		limit = 200
	}
	rows, err := s.db.Query(
		`SELECT `+messageColumns+
			` FROM messages ORDER BY created_unix DESC LIMIT ?`,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectMessages(rows)
}

// search filters messages by sender/recipient/subject substring + lookback.
func (s *store) search(sender, recipient, subject string, days, limit int) ([]Message, error) {
	if err := s.ensureSchema(); err != nil {
		return nil, err
	}
	if days <= 0 {
		days = 7
	}
	if days > 365 {
		days = 365
	}
	if limit <= 0 || limit > 500 {
		limit = 100
	}
	conds := []string{"created_unix >= CAST(strftime('%s', 'now', ?) AS INTEGER)"}
	args := []any{fmt.Sprintf("-%d days", days)}
	if sender != "" {
		conds = append(conds, "sender = ?")
		args = append(args, sender)
	}
	if recipient != "" {
		conds = append(conds, "recipient = ?")
		args = append(args, recipient)
	}
	if subject != "" {
		conds = append(conds, "subject LIKE ?")
		args = append(args, "%"+subject+"%")
	}
	q := `SELECT ` + messageColumns + ` FROM messages WHERE ` +
		strings.Join(conds, " AND ") +
		` ORDER BY created_unix DESC LIMIT ?`
	args = append(args, limit)
	rows, err := s.db.Query(q, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	return collectMessages(rows)
}

func collectMessages(rows *sql.Rows) ([]Message, error) {
	out := []Message{}
	for rows.Next() {
		m, err := scanMessage(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// getMessage fetches one message by id; returns sql.ErrNoRows if missing.
func (s *store) getMessage(id string) (Message, error) {
	if err := s.ensureSchema(); err != nil {
		return Message{}, err
	}
	row := s.db.QueryRow(
		`SELECT `+messageColumns+` FROM messages WHERE id = ?`,
		id,
	)
	return scanMessage(row)
}

// insertMessage adds a new message and returns its id.
func (s *store) insertMessage(sender, recipient, priority, subject, body string, parentID *string) (string, error) {
	if err := s.ensureSchema(); err != nil {
		return "", err
	}
	id := uuid.NewString()
	status := "unread"
	if s.autoApprove && (priority == "action" || priority == "urgent") {
		status = "approved"
	}
	_, err := withRetry(func() (struct{}, error) {
		_, err := s.db.Exec(
			`INSERT INTO messages
                (id, sender, recipient, priority, subject, body, status, parent_id)
              VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
			id, sender, recipient, priority, subject, body, status, parentID,
		)
		return struct{}{}, err
	})
	if err != nil {
		return "", err
	}
	return id, nil
}

// updateStatus changes a message's status. Returns sql.ErrNoRows if the
// id doesn't exist.
func (s *store) updateStatus(id, status string) error {
	if err := s.ensureSchema(); err != nil {
		return err
	}
	res, err := withRetry(func() (sql.Result, error) {
		return s.db.Exec(`UPDATE messages SET status = ? WHERE id = ?`, status, id)
	})
	if err != nil {
		return err
	}
	n, err := res.RowsAffected()
	if err != nil {
		return err
	}
	if n == 0 {
		return sql.ErrNoRows
	}
	return nil
}

// stats returns counts by status across all messages.
type Stats struct {
	Total           int            `json:"total"`
	Unread          int            `json:"unread"`
	Read            int            `json:"read"`
	Approved        int            `json:"approved"`
	InProgress      int            `json:"in_progress"`
	Rejected        int            `json:"rejected"`
	Done            int            `json:"done"`
	PendingApproval int            `json:"pending_approval"`
	ByRecipient     map[string]int `json:"by_recipient"`
}

func (s *store) stats() (Stats, error) {
	if err := s.ensureSchema(); err != nil {
		return Stats{}, err
	}
	st := Stats{ByRecipient: map[string]int{}}

	// Status totals.
	rows, err := s.db.Query(`SELECT status, count(*) FROM messages GROUP BY status`)
	if err != nil {
		return st, err
	}
	for rows.Next() {
		var k string
		var v int
		if err := rows.Scan(&k, &v); err != nil {
			rows.Close()
			return st, err
		}
		st.Total += v
		switch k {
		case "unread":
			st.Unread = v
		case "read":
			st.Read = v
		case "approved":
			st.Approved = v
		case "in_progress":
			st.InProgress = v
		case "rejected":
			st.Rejected = v
		case "done":
			st.Done = v
		}
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return st, err
	}

	// Pending approval — unread action/urgent only.
	if err := s.db.QueryRow(`
		SELECT count(*) FROM messages
		WHERE status = 'unread' AND priority IN ('action','urgent')
	`).Scan(&st.PendingApproval); err != nil {
		return st, err
	}

	// Per-recipient counts of attention-worthy messages.
	r2, err := s.db.Query(`
		SELECT recipient, count(*) FROM messages
		WHERE status IN ('unread','approved')
		GROUP BY recipient
	`)
	if err != nil {
		return st, err
	}
	defer r2.Close()
	for r2.Next() {
		var k string
		var v int
		if err := r2.Scan(&k, &v); err != nil {
			return st, err
		}
		st.ByRecipient[k] = v
	}
	return st, r2.Err()
}

// ErrNotFound wraps sql.ErrNoRows for cleaner error matching at higher layers.
var ErrNotFound = errors.New("message not found")

func translateNotFound(err error) error {
	if errors.Is(err, sql.ErrNoRows) {
		return ErrNotFound
	}
	return err
}

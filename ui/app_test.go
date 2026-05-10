// Go-side parity tests covering the contracts that mirror the Python
// side. Closes the v0.3.4 acknowledged gap (no Go test for the byte/char
// fix) and the v0.3.5 regex anchor parity check.

package main

import (
	"database/sql"
	"strings"
	"testing"
	"unicode/utf8"

	_ "modernc.org/sqlite"
)

// --- Length validation: characters, not bytes ----------------------------

func TestValidateLengthsASCII(t *testing.T) {
	if err := validateLengths(strings.Repeat("x", maxSubjectLen), ""); err != nil {
		t.Fatalf("subject at cap should pass: %v", err)
	}
	if err := validateLengths(strings.Repeat("x", maxSubjectLen+1), ""); err == nil {
		t.Fatal("subject over cap should fail")
	}
	if err := validateLengths("ok", strings.Repeat("x", maxBodyLen)); err != nil {
		t.Fatalf("body at cap should pass: %v", err)
	}
	if err := validateLengths("ok", strings.Repeat("x", maxBodyLen+1)); err == nil {
		t.Fatal("body over cap should fail")
	}
}

func TestValidateLengthsCountsRunesNotBytes(t *testing.T) {
	// Tornado emoji is 4 UTF-8 bytes per rune. With len() we'd count
	// 2000 bytes for 500 emoji and reject; with utf8.RuneCountInString
	// we count 500 runes and accept. Python's len(str) is rune-equivalent,
	// so this test pins parity.
	emoji := "🌪"
	if utf8.RuneCountInString(emoji) != 1 {
		t.Fatalf("expected 1 rune, got %d", utf8.RuneCountInString(emoji))
	}
	if len(emoji) != 4 {
		t.Fatalf("expected 4 bytes, got %d (test assumption broken)", len(emoji))
	}

	// 500 emoji subject = 500 runes (at cap) but 2000 bytes (over byte-cap).
	// Must pass.
	if err := validateLengths(strings.Repeat(emoji, maxSubjectLen), ""); err != nil {
		t.Fatalf("500 emoji subject should pass under rune count: %v", err)
	}
	// 501 emoji = 501 runes, must fail.
	if err := validateLengths(strings.Repeat(emoji, maxSubjectLen+1), ""); err == nil {
		t.Fatal("501 emoji subject should fail")
	}
}

func TestValidateLengthsZWJFamily(t *testing.T) {
	// 👨‍👩‍👧‍👦 is one grapheme cluster but 7 code points (4 person +
	// 3 ZWJ). RuneCountInString counts 7. We document this as
	// code-points-not-graphemes; this test pins that contract.
	family := "👨‍👩‍👧‍👦"
	if utf8.RuneCountInString(family) != 7 {
		t.Fatalf("expected 7 runes, got %d", utf8.RuneCountInString(family))
	}
	// 71 families = 497 runes — under the 500 cap.
	if err := validateLengths(strings.Repeat(family, 71), ""); err != nil {
		t.Fatalf("71 ZWJ families should pass: %v", err)
	}
	// 72 families = 504 runes — over the cap.
	if err := validateLengths(strings.Repeat(family, 72), ""); err == nil {
		t.Fatal("72 ZWJ families should fail (504 runes > 500 cap)")
	}
}

// --- Operator name validation: parity with Python briefs.NAME_RE --------

func TestValidateOperatorNameAcceptsValid(t *testing.T) {
	for _, good := range []string{"operator", "alice", "ki7mt", "ops-lead", "dev_1", "a"} {
		if err := validateOperatorName(good); err != nil {
			t.Errorf("validateOperatorName(%q) should pass: %v", good, err)
		}
	}
}

func TestValidateOperatorNameRejectsReserved(t *testing.T) {
	if err := validateOperatorName("all"); err == nil {
		t.Fatal("validateOperatorName(\"all\") should reject — 'all' is reserved for broadcast")
	}
}

func TestValidateOperatorNameRejectsInvalidChars(t *testing.T) {
	for _, bad := range []string{
		"",          // empty
		"1bad",      // leading digit
		"with space",
		"with.dot",
		"with/slash",
		"Operator", // uppercase (caller is expected to lowercase first)
	} {
		if err := validateOperatorName(bad); err == nil {
			t.Errorf("validateOperatorName(%q) should reject", bad)
		}
	}
}

func TestNameREStrictEndAnchor(t *testing.T) {
	// Go's regexp `$` is already strict end-of-string — but this test
	// pins the behavior so the parity contract with Python's `\Z` fix
	// can't drift. A trailing newline must be rejected.
	if nameRE.MatchString("alice\n") {
		t.Fatal("nameRE should reject trailing newline (parity with Python's \\Z)")
	}
	if nameRE.MatchString("alice\r") {
		t.Fatal("nameRE should reject trailing carriage return")
	}
	if nameRE.MatchString("alice\t") {
		t.Fatal("nameRE should reject trailing tab")
	}
	if nameRE.MatchString("alice ") {
		t.Fatal("nameRE should reject trailing space")
	}
	if !nameRE.MatchString("alice") {
		t.Fatal("nameRE should accept a normal name")
	}
}

// --- Migration: legacy schema gets parent_id + created_unix added --------

// TestMigrateLegacyDB seeds a database with the v0.2.1-era schema (no
// parent_id, no created_unix) and verifies the Go store's ensureSchema
// adds the missing columns idempotently. Closes a real gap from the
// post-v0.4.1 enterprise review: previously only the Python side
// migrated, so a user opening the Wails UI against an old DB would
// hit "no such column" on every read.
func TestMigrateLegacyDB(t *testing.T) {
	dir := t.TempDir()
	dbPath := dir + "/legacy.db"

	// Seed with the v0.2.1 schema — no parent_id, no created_unix.
	legacy, err := sql.Open("sqlite", "file:"+dbPath+"?_pragma=journal_mode(WAL)")
	if err != nil {
		t.Fatalf("open legacy: %v", err)
	}
	if _, err := legacy.Exec(`
		CREATE TABLE messages (
			id TEXT PRIMARY KEY,
			timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
			sender TEXT NOT NULL,
			recipient TEXT NOT NULL,
			priority TEXT NOT NULL CHECK(priority IN ('info','action','urgent')),
			status TEXT NOT NULL DEFAULT 'unread',
			subject TEXT NOT NULL,
			body TEXT NOT NULL
		);
	`); err != nil {
		t.Fatalf("create legacy schema: %v", err)
	}
	if _, err := legacy.Exec(`
		INSERT INTO messages (id, sender, recipient, priority, status, subject, body)
		VALUES ('legacy-1', 'alice', 'bob', 'info', 'unread', 'old', 'pre-migration')
	`); err != nil {
		t.Fatalf("seed legacy row: %v", err)
	}
	_ = legacy.Close()

	// Open the same DB with the new store; ensureSchema must migrate.
	s, err := newStore(dbPath)
	if err != nil {
		t.Fatalf("newStore: %v", err)
	}
	defer s.close()
	if err := s.ensureSchema(); err != nil {
		t.Fatalf("ensureSchema on legacy DB: %v", err)
	}

	// Verify both columns exist post-migration.
	cols, err := tableColumns(s.db, "messages")
	if err != nil {
		t.Fatalf("tableColumns: %v", err)
	}
	for _, want := range []string{"parent_id", "created_unix"} {
		if _, ok := cols[want]; !ok {
			t.Errorf("expected column %q after migration, missing", want)
		}
	}

	// The legacy row should have created_unix backfilled from timestamp,
	// not NULL — otherwise listForRecipient ORDER BY created_unix would
	// surface NULL-sort surprises.
	var cu sql.NullInt64
	if err := s.db.QueryRow("SELECT created_unix FROM messages WHERE id = 'legacy-1'").Scan(&cu); err != nil {
		t.Fatalf("read created_unix: %v", err)
	}
	if !cu.Valid || cu.Int64 == 0 {
		t.Errorf("created_unix should be backfilled from timestamp, got valid=%v value=%d", cu.Valid, cu.Int64)
	}

	// And the read path that depends on created_unix must work end-to-end.
	rows, err := s.listForRecipient("bob")
	if err != nil {
		t.Fatalf("listForRecipient on migrated DB: %v", err)
	}
	if len(rows) != 1 || rows[0].ID != "legacy-1" {
		t.Errorf("expected legacy row visible to bob, got %+v", rows)
	}

	// Re-running ensureSchema on an already-migrated DB is a no-op.
	s2, err := newStore(dbPath)
	if err != nil {
		t.Fatalf("re-open: %v", err)
	}
	defer s2.close()
	if err := s2.ensureSchema(); err != nil {
		t.Fatalf("ensureSchema idempotent re-run: %v", err)
	}
}

// --- Stats consistency: per-recipient count matches recipient view -------

// TestStatsByRecipientMatchesListForRecipient pins the contract from
// the post-v0.4.1 review: the sidebar badge count for a recipient must
// equal what listForRecipient returns for that same recipient. Pre-fix,
// stats() counted every unread+approved row, but listForRecipient gates
// unread to priority=info — so an unapproved action/urgent message
// inflated the badge but didn't appear in the recipient's actual view.
func TestStatsByRecipientMatchesListForRecipient(t *testing.T) {
	dir := t.TempDir()
	s, err := newStore(dir + "/inbox.db")
	if err != nil {
		t.Fatalf("newStore: %v", err)
	}
	defer s.close()
	if err := s.ensureSchema(); err != nil {
		t.Fatalf("ensureSchema: %v", err)
	}

	// Three messages to bob:
	//   - info / unread       → visible to bob, counted in stats
	//   - action / unread     → NOT visible to bob (awaiting approval),
	//                           also NOT counted (the post-fix predicate)
	//   - info / approved     → visible to bob, counted
	for _, m := range []struct{ priority, status string }{
		{"info", "unread"},
		{"action", "unread"},
		{"info", "approved"},
	} {
		if _, err := s.db.Exec(`
			INSERT INTO messages (id, sender, recipient, priority, status, subject, body)
			VALUES (?, 'alice', 'bob', ?, ?, 'subj', '')
		`, "m-"+m.priority+"-"+m.status, m.priority, m.status); err != nil {
			t.Fatalf("seed: %v", err)
		}
	}

	listed, err := s.listForRecipient("bob")
	if err != nil {
		t.Fatalf("listForRecipient: %v", err)
	}
	st, err := s.stats()
	if err != nil {
		t.Fatalf("stats: %v", err)
	}

	listedCount := len(listed)
	statsCount := st.ByRecipient["bob"]
	if listedCount != statsCount {
		t.Errorf(
			"sidebar badge / inbox view mismatch for bob: stats says %d, listForRecipient says %d",
			statsCount, listedCount,
		)
	}
	if listedCount != 2 {
		t.Errorf("expected 2 visible messages to bob (info-unread + info-approved), got %d", listedCount)
	}
}

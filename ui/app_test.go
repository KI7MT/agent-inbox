// Go-side parity tests covering the contracts that mirror the Python
// side. Closes the v0.3.4 acknowledged gap (no Go test for the byte/char
// fix) and the v0.3.5 regex anchor parity check.

package main

import (
	"strings"
	"testing"
	"unicode/utf8"
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

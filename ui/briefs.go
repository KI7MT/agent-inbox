// Agent registry from markdown brief files. Mirrors briefs.py: the
// filename (without .md) is the canonical agent name; names must match
// ^[a-z][a-z0-9_-]*$; the reserved name "all" is the broadcast target
// and cannot be a brief filename.

package main

import (
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var nameRE = regexp.MustCompile(`^[a-z][a-z0-9_-]*$`)
var reservedNames = map[string]bool{"all": true}

// validateOperatorName mirrors briefs.py:operator_name's validation —
// rejects reserved names like "all" and any name that doesn't match
// nameRE. Bad config is rejected loudly at startup rather than producing
// a quietly-broken installation.
func validateOperatorName(name string) error {
	if reservedNames[name] {
		return fmt.Errorf(
			"AGENT_INBOX_OPERATOR cannot be a reserved name (got %q)", name,
		)
	}
	if !nameRE.MatchString(name) {
		return fmt.Errorf(
			"AGENT_INBOX_OPERATOR=%q doesn't match %s — use lowercase "+
				"letters/digits/hyphen/underscore, starting with a letter",
			name, nameRE.String(),
		)
	}
	return nil
}

// loadAgents returns the sorted list of valid agent names found in the
// briefs directory. Files whose stem doesn't match `nameRE` or matches a
// reserved name are skipped silently.
func loadAgents() []string {
	dir := briefsDir()
	entries, err := os.ReadDir(dir)
	if err != nil {
		return nil
	}
	seen := make(map[string]bool)
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		name := strings.TrimSuffix(e.Name(), filepath.Ext(e.Name()))
		if filepath.Ext(e.Name()) != ".md" {
			continue
		}
		name = strings.ToLower(name)
		if reservedNames[name] || !nameRE.MatchString(name) {
			continue
		}
		seen[name] = true
	}
	out := make([]string, 0, len(seen))
	for n := range seen {
		out = append(out, n)
	}
	sort.Strings(out)
	return out
}

// readBrief returns the markdown content of an agent's brief, or empty
// string if missing.
func readBrief(name string) string {
	dir := briefsDir()
	p := filepath.Join(dir, name+".md")
	b, err := os.ReadFile(p)
	if err != nil {
		return ""
	}
	return string(b)
}

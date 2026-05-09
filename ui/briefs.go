// Agent registry from markdown brief files. Mirrors briefs.py: the
// filename (without .md) is the canonical agent name; names must match
// ^[a-z][a-z0-9_-]*$; the reserved name "all" is the broadcast target
// and cannot be a brief filename.

package main

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
)

var nameRE = regexp.MustCompile(`^[a-z][a-z0-9_-]*$`)
var reservedNames = map[string]bool{"all": true}

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

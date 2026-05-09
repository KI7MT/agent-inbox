// Path resolution. Mirrors src/agent_inbox/db.py and briefs.py so the
// Python and Go halves agree on where the inbox SQLite file and brief
// files live for a given OS.
//
// Linux:   ~/.config/agent-inbox/briefs/  +  ~/.local/share/agent-inbox/inbox.db
// macOS:   ~/Library/Application Support/agent-inbox/{briefs,inbox.db}
// Windows: %APPDATA%\agent-inbox\briefs\  +  %LOCALAPPDATA%\agent-inbox\inbox.db
//
// Env-var overrides:
//   AGENT_INBOX_BRIEFS    — directory containing brief markdown files
//   AGENT_INBOX_DB        — SQLite file path
//   AGENT_INBOX_OPERATOR  — canonical operator name (defaults to "operator")

package main

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"

	"github.com/adrg/xdg"
)

const appName = "agent-inbox"

// briefsDir returns the directory containing agent brief markdown files.
func briefsDir() string {
	if v := os.Getenv("AGENT_INBOX_BRIEFS"); v != "" {
		return expandHome(v)
	}
	switch runtime.GOOS {
	case "darwin":
		home, _ := os.UserHomeDir()
		return filepath.Join(home, "Library", "Application Support", appName, "briefs")
	case "windows":
		base := os.Getenv("APPDATA")
		if base == "" {
			home, _ := os.UserHomeDir()
			base = filepath.Join(home, "AppData", "Roaming")
		}
		return filepath.Join(base, appName, "briefs")
	default:
		return filepath.Join(xdg.ConfigHome, appName, "briefs")
	}
}

// dbPath returns the SQLite database file path.
func dbPath() string {
	if v := os.Getenv("AGENT_INBOX_DB"); v != "" {
		return expandHome(v)
	}
	switch runtime.GOOS {
	case "darwin":
		home, _ := os.UserHomeDir()
		return filepath.Join(home, "Library", "Application Support", appName, "inbox.db")
	case "windows":
		base := os.Getenv("LOCALAPPDATA")
		if base == "" {
			home, _ := os.UserHomeDir()
			base = filepath.Join(home, "AppData", "Local")
		}
		return filepath.Join(base, appName, "inbox.db")
	default:
		return filepath.Join(xdg.DataHome, appName, "inbox.db")
	}
}

// operatorName returns the canonical name for the human user.
func operatorName() string {
	v := os.Getenv("AGENT_INBOX_OPERATOR")
	if v == "" {
		return "operator"
	}
	return strings.ToLower(v)
}

// expandHome expands a leading ~ or ~/ in p to the user's home directory.
func expandHome(p string) string {
	if !strings.HasPrefix(p, "~") {
		return p
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return p
	}
	if p == "~" {
		return home
	}
	if strings.HasPrefix(p, "~/") {
		return filepath.Join(home, p[2:])
	}
	return p
}

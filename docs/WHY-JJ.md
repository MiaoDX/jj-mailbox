# Why jj (not plain git)?

jj-mailbox uses [jj (Jujutsu)](https://github.com/jj-vcs/jj) instead of plain git for five key reasons:

1. **Concurrent safety** — jj is designed to be safe when multiple processes access the repo simultaneously. Git is not.
2. **First-class conflicts** — when two agents push at the same time, jj preserves both changes. Git would reject the push.
3. **Operation log** — every action is recorded and reversible. Full audit trail for free.
4. **Working copy as commit** — file changes are automatically captured. No `git add` needed.
5. **Dropbox/rsync safe** — jj repos can be synced via file copy without corruption. Git repos cannot.

## Design Principles

- **Files are the API** — agents only need to read and write files
- **Zero new abstractions** — no daemons, no databases, no custom wire protocols
- **Agent-agnostic** — works with OpenClaw, Claude Code, Codex, or any file-aware agent
- **jj handles the hard parts** — conflict resolution, history, concurrent safety
- **Graceful degradation** — works with plain git too (less safe, but functional)

## Inspiration

- [Maildir](https://en.wikipedia.org/wiki/Maildir) — the original file-based mailbox (1995)
- [Plan 9](https://en.wikipedia.org/wiki/9P_(protocol)) — everything is a file
- [Claude Code Agent Teams](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html) — JSON files as coordination substrate
- [jj (Jujutsu)](https://github.com/jj-vcs/jj) — the VCS that makes this safe

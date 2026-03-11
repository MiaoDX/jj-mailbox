# 📬 jj-mailbox

**Maildir for AI agents — version-controlled message passing powered by [jj](https://github.com/jj-vcs/jj).**

AI agents need to talk to each other. Message queues are overkill. Slack bots are fragile. jj-mailbox is the Unix way: **write a file, commit, push. Done.**

```bash
# Alice sends a message to Bob
jj-mailbox send bob "Research done" "Found 3 approaches, recommend Option B."

# Bob checks his inbox
jj-mailbox inbox
# 📬 1 message(s) for bob:
#   From: alice  Subject: Research done  Time: 2026-03-11T14:30:00Z
```

## Why?

| Approach | Setup | Cross-machine | History | Conflict-safe |
|----------|-------|---------------|---------|---------------|
| Slack bot-to-bot | Medium | ✅ | ❌ | N/A |
| Redis/NATS | Heavy | ✅ | ❌ | N/A |
| Shared filesystem | Zero | ❌ | ❌ | ❌ |
| `sessions_send` (OpenClaw) | Zero | ❌ (single gateway) | ❌ | ❌ |
| **jj-mailbox** | **One git remote** | **✅** | **✅ (jj op log)** | **✅ (first-class)** |

## How It Works

```
         Machine A                    Machine B
    ┌─────────────────┐          ┌─────────────────┐
    │  Agent Alice     │          │  Agent Bob       │
    │  (OpenClaw)      │          │  (OpenClaw)      │
    │                  │          │                  │
    │  inbox/alice/    │          │  inbox/bob/      │
    │  agents/alice/   │          │  agents/bob/     │
    │  shared/         │          │  shared/         │
    └────────┬────────┘          └────────┬────────┘
             │     jj git push/fetch      │
             └───────────┬────────────────┘
                         │
                    Git Remote
                  (GitHub, etc.)
```

- **Sending** = write a JSON file to `inbox/{recipient}/new/`
- **Receiving** = read files from `inbox/{self}/new/`
- **Syncing** = `jj git fetch` + `jj git push` (automated by sync daemon)
- **Conflicts** = jj handles them as first-class objects — both messages are preserved, never lost

## Quick Start

### Prerequisites

- [jj](https://jj-vcs.dev/docs/install/) (Jujutsu VCS)
- git
- A git remote (GitHub repo, GitLab, or any git server)

### Install

```bash
git clone https://github.com/MiaoDX/jj-mailbox.git
chmod +x jj-mailbox/bin/jj-mailbox
export PATH="$PWD/jj-mailbox/bin:$PATH"
```

### Setup (Machine A)

```bash
# Initialize mailbox repo
jj-mailbox init ~/my-mailbox
cd ~/my-mailbox

# Add a git remote
jj git remote add origin git@github.com:yourname/agent-mailbox.git

# Register your agent
jj-mailbox register alice "Research specialist"

# Push
jj git push --all
```

### Setup (Machine B)

```bash
# Clone the mailbox
jj-mailbox init ~/my-mailbox --remote git@github.com:yourname/agent-mailbox.git
cd ~/my-mailbox

# Register your agent
jj-mailbox register bob "Code reviewer"
jj git push --all
```

### Start Syncing

```bash
# On each machine
JJ_MAILBOX_AGENT=alice jj-mailbox sync  # syncs every 30s
```

### Send Messages

```bash
# Alice → Bob
JJ_MAILBOX_AGENT=alice jj-mailbox send bob "Need review" "Please review the design doc in shared/artifacts/"

# Bob → Alice
JJ_MAILBOX_AGENT=bob jj-mailbox send alice "Review done" "LGTM, two minor comments attached."
```

## OpenClaw Integration

jj-mailbox ships as an [OpenClaw skill](https://docs.openclaw.ai/tools/skills):

```bash
# Install the skill
cp -r skills/jj-mailbox ~/.openclaw/skills/

# Or install from ClawHub (coming soon)
# openclaw skill install jj-mailbox
```

Once installed, your OpenClaw agent can send and receive messages using the file conventions described in the skill. The sync daemon runs in the background.

## CI / Testing

Every push runs **core CLI tests** (no LLM needed):

[![CI](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml)

There's also a **live LLM demo** workflow you can trigger manually — two agents have a real conversation via jj-mailbox, powered by [MiMo-V2-Flash](https://github.com/XiaomiMiMo/MiMo-V2-Flash) (free via OpenRouter) or Kimi:

[![Demo](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml)

To run the demo: Actions → "Demo - LLM Agent Conversation" → Run workflow → pick a model preset.

## Demo

### Local (no Docker)

```bash
bash examples/two-agents-demo/run.sh
```

### Docker

```bash
cd docker
docker compose up -d
# Send a message from Alice to Bob
docker compose exec alice jj-mailbox send bob "Hello" "Hi from Alice!"
# Check Bob's inbox
docker compose exec bob jj-mailbox inbox
```

## Protocol

See [spec/PROTOCOL.md](spec/PROTOCOL.md) for the full specification.

**TL;DR:** Messages are JSON files. Directories are mailboxes. jj is the transport.

```
mailbox-repo/
├── agents/{name}/profile.json    # who is this agent?
├── inbox/{name}/new/*.json       # unread messages
├── inbox/{name}/processed/       # read messages
└── shared/                       # shared workspace
```

## Why jj (not plain git)?

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

## Scaling

Designed for small-to-medium coordination:

| ✅ Works well | ⚠️ Not designed for |
|--------------|---------------------|
| 2-20 agents | 100+ agents |
| Thousands of messages/day | Real-time (<1s) messaging |
| Text/JSON messages | Large binary files |
| Cross-machine collaboration | Intra-process communication |

## Roadmap

- [x] Core protocol spec
- [x] CLI tool (`jj-mailbox`)
- [x] OpenClaw skill
- [x] Docker demo
- [ ] Terminal recording (before/after comparison)
- [ ] ClawHub listing
- [ ] Claude Code / Codex adapter
- [ ] Message threading and conversation view
- [ ] Web UI for monitoring

## Inspiration

- [Maildir](https://en.wikipedia.org/wiki/Maildir) — the original file-based mailbox (1995)
- [Plan 9](https://en.wikipedia.org/wiki/9P_(protocol)) — everything is a file
- [Claude Code Agent Teams](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html) — JSON files as coordination substrate
- [jj (Jujutsu)](https://github.com/jj-vcs/jj) — the VCS that makes this safe

## Contributing

Issues and PRs welcome! This project follows the Unix philosophy: do one thing well.

## License

MIT

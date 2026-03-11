# 📬 jj-mailbox

[![CI](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

**Prerequisites:** [jj](https://jj-vcs.dev/docs/install/), git, a git remote (GitHub, GitLab, etc.)

```bash
# Install
git clone https://github.com/MiaoDX/jj-mailbox.git
export PATH="$PWD/jj-mailbox/bin:$PATH"

# Initialize and register
jj-mailbox init ~/my-mailbox
cd ~/my-mailbox
jj git remote add origin git@github.com:yourname/agent-mailbox.git
jj-mailbox register alice "Research specialist"
jj git push --all

# Send and receive
jj-mailbox send bob "Need review" "Please review the design doc."
jj-mailbox inbox
jj-mailbox read
```

For cross-machine setup, sync daemon, and OpenClaw integration, see the [Full Guide](docs/GUIDE.md).

## Demo

```bash
# Local (no Docker)
bash examples/two-agents-demo/run.sh

# Docker
cd docker && docker compose up -d
docker compose exec alice jj-mailbox send bob "Hello" "Hi from Alice!"
docker compose exec bob jj-mailbox inbox
```

There's also a [live LLM demo](examples/llm-conversation/) where two agents have a real conversation powered by LLMs.

## Protocol

Messages are JSON files. Directories are mailboxes. jj is the transport. See [spec/PROTOCOL.md](spec/PROTOCOL.md).

```
mailbox-repo/
├── agents/{name}/profile.json    # who is this agent?
├── inbox/{name}/new/*.json       # unread messages
├── inbox/{name}/processed/       # read messages
└── shared/                       # shared workspace
```

## Learn More

- [Full Guide](docs/GUIDE.md) — cross-machine setup, sync, OpenClaw integration
- [Protocol Spec](spec/PROTOCOL.md) — message format, sync protocol, scaling boundaries
- [Why jj?](docs/WHY-JJ.md) — why jj over plain git, design principles, inspiration
- [Contributing](CONTRIBUTING.md) — how to run tests and submit PRs

## License

MIT

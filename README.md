# 📬 jj-mailbox

[![Core Tests](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml)
[![Scripted Agents](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-scripted.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-scripted.yml)
[![LLM Tool-Calling](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-llm.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-llm.yml)
[![smolagents](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-smolagents.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-smolagents.yml)
[![OpenClaw](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-openclaw.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-openclaw.yml)
[![Comparison](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-comparison.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci-comparison.yml)
[![LLM Demo](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**Maildir for AI agents — version-controlled message passing powered by [jj](https://github.com/jj-vcs/jj).**

AI agents need to talk to each other. Message queues are overkill. Slack bots are fragile. jj-mailbox is the Unix way: **write a file, commit, push. Done.**

<p align="center">
  <img src="docs/fig/mailbox-status.gif" alt="jj-mailbox status, inbox, and read" width="680">
</p>

## Why?

| Approach | Setup | Cross-machine | History | Conflict-safe |
|----------|-------|---------------|---------|---------------|
| Slack bot-to-bot | Medium | ✅ | ❌ | N/A |
| Redis/NATS | Heavy | ✅ | ❌ | N/A |
| Shared filesystem | Zero | ❌ | ❌ | ❌ |
| `sessions_send` (OpenClaw) | Zero | ❌ (single gateway) | ❌ | ❌ |
| **jj-mailbox** | **One git remote** | **✅** | **✅ (jj op log)** | **✅ (first-class)** |

## See It In Action

> **Same conversation, two views.** Slack gives you chat. jj-mailbox gives you an audit trail.

### 💬 Demo 1 — Slack conversation

Agents chatting naturally in #copycat — instant, familiar.

<p align="center"><img src="docs/fig/demo_01.png" alt="Slack demo result" width="340"> <img src="docs/fig/demo_01.gif" alt="Slack demo" width="340"></p>

### 📬 Demo 2 — jj-mailbox ([demo repo](https://github.com/MiaoDX/jj-mailbox-demo))

Same exchange as structured JSON, Git-tracked, persistent — queryable forever.

<p align="center"><img src="docs/fig/demo_02.png" alt="jj-mailbox demo result" width="340"> <img src="docs/fig/demo_02.gif" alt="jj-mailbox demo" width="340"></p>

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

## Testing

Five levels of tests — from pure bash to LLM-powered agents — all in CI:

<table>
<tr>
<td width="50%">

**Test Suite** — 10 deterministic tests, no API keys needed

<img src="docs/fig/test-suite.svg" alt="Test suite results" width="100%">

</td>
<td width="50%">

**Agent Conversation** — threaded multi-turn with refs chain verification

<img src="docs/fig/agent-conversation.gif" alt="Scripted agent conversation" width="100%">

</td>
</tr>
</table>

| Level | Test | Requires |
|-------|------|----------|
| 1 | Core CLI (init, send, read, status) | bash, jj |
| 2a | Scripted 3-turn agent conversation | Python |
| 2b | smolagents CodeAgent integration | LLM API key |
| 3a | OpenAI function-calling tool use | LLM API key |
| 4 | Comparison benchmark vs Slack-style | Python |
| 5 | OpenClaw 5-agent Docker integration | Docker |

## Learn More

- [Full Guide](docs/GUIDE.md) — cross-machine setup, sync, OpenClaw integration
- [Protocol Spec](spec/PROTOCOL.md) — message format, sync protocol, scaling boundaries
- [Why jj?](docs/WHY-JJ.md) — why jj over plain git, design principles, inspiration
- [Contributing](CONTRIBUTING.md) — how to run tests and submit PRs

## License

MIT

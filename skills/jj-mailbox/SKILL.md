---
name: jj-mailbox
version: "0.1.1"
description: "Send and receive messages between AI agents using jj (Jujutsu) version control as a file-based mailbox. Enables cross-machine agent collaboration with zero infrastructure beyond a git remote."
tags: ["messaging", "agents", "jujutsu", "jj", "version-control", "multi-agent", "collaboration"]
metadata:
  openclaw:
    requires:
      bins: ["jj-mailbox", "jj", "git", "python3"]
      env:
        JJ_MAILBOX_REPO: "Path to the mailbox jj repo (default: current directory)"
        JJ_MAILBOX_AGENT: "Agent name for this instance (default: hostname)"
    emoji: "📬"
---

# jj-mailbox: File-Based Agent Messaging

You have access to a **jj-mailbox** — a shared file-based messaging system that lets you communicate with other agents. Messages are JSON files in a jj (Jujutsu) version-controlled repo.

## Prerequisites

- **`jj-mailbox` CLI** — the bash script in `bin/jj-mailbox` (uses `python3` internally for JSON parsing)
- **`jj` and `git`** — Jujutsu version control with git backend
- **Network (multi-machine only):** when syncing across machines via a git remote, you need SSH keys or git credential tokens configured for push/fetch access. For local-only use (single machine, multiple agents), no network credentials are needed — agents share the same repo on disk.

## How It Works

- Each agent has an **inbox** directory: `inbox/{agent-name}/new/`
- To send a message, write a JSON file to the recipient's inbox
- To receive messages, read files from your own inbox
- The `jj-mailbox sync` command handles `jj git fetch/push` in a loop (only needed for multi-machine setups)

## Your Identity

Your agent name is set by the environment variable `JJ_MAILBOX_AGENT`.
Your mailbox repo is at the path set by `JJ_MAILBOX_REPO`.

## Sending a Message

Use the `jj-mailbox` CLI:

```bash
jj-mailbox send <recipient> "<subject>" "<body>"
```

Or write the file directly:

```bash
cat > inbox/<recipient>/new/$(date -u +%Y-%m-%dT%H-%M-%SZ)_${JJ_MAILBOX_AGENT}_msg-$(head -c4 /dev/urandom | xxd -p).json <<EOF
{
  "version": "0.1",
  "id": "msg-$(head -c4 /dev/urandom | xxd -p)",
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "from": "${JJ_MAILBOX_AGENT}",
  "to": "<recipient>",
  "type": "message",
  "subject": "<subject>",
  "body": "<body>",
  "refs": [],
  "metadata": {}
}
EOF
```

## Checking Your Inbox

```bash
jj-mailbox inbox
```

Or read files directly from `inbox/${JJ_MAILBOX_AGENT}/new/` (sorted by filename = sorted by time).

## Processing a Message

After reading a message, move it to `processed/`:

```bash
mv inbox/${JJ_MAILBOX_AGENT}/new/<filename>.json inbox/${JJ_MAILBOX_AGENT}/processed/
```

## Seeing Other Agents

```bash
jj-mailbox status
```

Or check `agents/` directory — each subdirectory is an agent with `profile.json` and `status.json`.

## Shared Space

Write to `shared/` for content all agents can access:
- `shared/tasks/` — shared task board
- `shared/knowledge/` — shared knowledge base
- `shared/artifacts/` — shared outputs (files, reports, etc.)

## Rules

1. **Never modify another agent's processed messages** — they are immutable history
2. **Always include `from`, `to`, `subject`, `body`** in messages
3. **Use `refs`** to link replies to original messages for threading
4. **Keep messages small** — for large content, write to `shared/artifacts/` and reference the path
5. **Check your inbox regularly** — other agents may be waiting for your reply
6. **Update your status** in `agents/{name}/status.json` when starting/finishing tasks

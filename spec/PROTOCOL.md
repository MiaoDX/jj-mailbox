# jj-mailbox Protocol Specification v0.1

> File-based message passing for AI agents, powered by Jujutsu (jj).

## Design Principles

1. **Files are the API** — agents only need to read and write files
2. **Zero new abstractions** — no daemons, no databases, no custom protocols
3. **jj handles the hard parts** — conflict resolution, history, concurrent safety
4. **Agent-agnostic** — works with OpenClaw, Claude Code, Codex, or any file-aware agent

## Directory Structure

```
mailbox-repo/
├── .jj/                          # jj metadata (auto-managed)
├── .git/                         # git backend (auto-managed)
├── agents/
│   ├── alice/
│   │   ├── profile.json          # agent identity & capabilities
│   │   └── status.json           # current status (online/busy/offline)
│   └── bob/
│       ├── profile.json
│       └── status.json
├── inbox/
│   ├── alice/                    # messages TO alice
│   │   ├── new/                  # unread messages
│   │   └── processed/            # read messages (kept for history)
│   └── bob/
│       ├── new/
│       └── processed/
├── shared/                       # shared workspace (all agents can read/write)
│   ├── tasks/                    # shared task board
│   ├── knowledge/                # shared knowledge base
│   └── artifacts/                # shared outputs
└── AGENTS.md                     # human-readable agent registry
```

## Message Format

Messages are JSON files in `inbox/{recipient}/new/`.

### File Naming

```
{ISO-timestamp}_{sender}_{message-id}.json
```

Example:
```
2026-03-11T14-30-00Z_alice_msg-a1b2c3.json
```

Rules:
- Timestamp is UTC ISO 8601, colons replaced with hyphens for filesystem safety
- Message ID is a short random hex string (6+ chars)
- Underscore `_` separates fields

### Message Schema

```json
{
  "version": "0.1",
  "id": "msg-a1b2c3",
  "timestamp": "2026-03-11T14:30:00Z",
  "from": "alice",
  "to": "bob",
  "type": "message",
  "subject": "Research results on topic X",
  "body": "Here are my findings...",
  "refs": [],
  "metadata": {}
}
```

Fields:
| Field | Required | Description |
|-------|----------|-------------|
| `version` | yes | Protocol version (`"0.1"`) |
| `id` | yes | Unique message ID |
| `timestamp` | yes | UTC ISO 8601 |
| `from` | yes | Sender agent name |
| `to` | yes | Recipient agent name |
| `type` | yes | `message`, `task`, `reply`, `broadcast`, `idle`, `approval_request`, `approval_response`, `shutdown` |
| `subject` | no | Short summary |
| `body` | yes | Message content (plain text or markdown) |
| `refs` | no | Array of referenced message IDs (for threading) |
| `metadata` | no | Arbitrary key-value pairs |

### Message Types

- **`message`** — general communication
- **`task`** — request for the recipient to do something
- **`reply`** — response to a previous message (use `refs` to link)
- **`broadcast`** — informational, no response expected
- **`idle`** — sender is available for more work
- **`approval_request`** — sender is asking for review or approval
- **`approval_response`** — review/approval decision with feedback
- **`shutdown`** — graceful wind-down signal

## Agent Profile

`agents/{name}/profile.json`:

```json
{
  "name": "alice",
  "description": "Research specialist",
  "capabilities": ["web-search", "summarization"],
  "platform": "openclaw",
  "created": "2026-03-11T00:00:00Z"
}
```

## Agent Status

`agents/{name}/status.json`:

```json
{
  "status": "online",
  "last_seen": "2026-03-11T14:30:00Z",
  "current_task": "Researching topic X"
}
```

Status values: `online`, `busy`, `idle`, `offline`, `waiting_approval`

## Operations

### Sending a Message

1. Create JSON file following the message schema
2. Write to `inbox/{recipient}/new/{filename}.json`
3. (Sync daemon handles commit + push)

### Receiving Messages

1. List files in `inbox/{self}/new/`
2. Read and process each file (oldest first, by timestamp)
3. Move processed files to `inbox/{self}/processed/`

### Broadcasting

Write the same message to multiple `inbox/{recipient}/new/` directories.
Or write to `shared/tasks/` for all agents to see.

## Sync Protocol

The sync daemon runs on each machine and performs:

```
loop every {interval} seconds:
  1. jj git fetch --all-remotes
  2. jj rebase  (auto-rebase working copy onto fetched changes)
  3. (agent does its work — reads inbox, writes messages)
  4. jj git push --all
```

### Conflict Resolution

jj's first-class conflict handling means:
- Two agents writing different files → auto-merged, no conflict
- Two agents writing to the same inbox simultaneously → both messages preserved
- Conflicting edits to shared files → jj records conflict, agents resolve later

### Sync Intervals

| Scenario | Recommended Interval |
|----------|---------------------|
| Active collaboration | 10-30 seconds |
| Background monitoring | 60-300 seconds |
| Manual/on-demand | Run `jj-mailbox sync` explicitly |

## Scaling Boundaries

This protocol is designed for **small-to-medium coordination**:
- ✅ 2-20 agents
- ✅ Hundreds to thousands of messages per day
- ⚠️ Not designed for real-time (<1s) messaging
- ⚠️ Not designed for large binary files (use refs/links instead)

## Compatibility

| Platform | Integration mode | Notes |
|----------|------------------|-------|
| OpenClaw | Native skill (`skills/jj-mailbox/`) | File-first workflow with sync daemon support |
| Codex / OpenAI function calling | Adapter (`examples/adapters/openai/tools.py`) | Exposes `send_message`, `read_inbox`, `write_artifact` |
| Claude Code / Anthropic tool_use | Adapter (`examples/adapters/claude_code/tools.py`) | Same mailbox operations via `input_schema` tools |
| Any file-aware agent | Direct protocol use | Read/write files in `inbox/`, `agents/`, `shared/` |

### Single-machine (OpenClaw multi-agent)

Same protocol, skip git push/fetch. Agents share the same local jj repo.
Use `jj workspace` for per-agent isolation if needed.

### Cross-machine

Each machine has a local clone. Sync via any git remote (GitHub, GitLab, self-hosted).

### Fallback to plain git

The protocol works with plain git too. jj adds safety (concurrent access, conflict handling, operation log) but is not strictly required.

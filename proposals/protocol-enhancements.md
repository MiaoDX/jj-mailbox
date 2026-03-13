# Proposal: Protocol Enhancements — Tasks, Message Types, Status, Hooks

> Extends jj-mailbox protocol for richer multi-agent coordination.
> Inspired by [Claude Code Agent Teams architecture](https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered).

## Background

Claude Code Agent Teams (v2.1.47) uses a file-based, decentralized coordination
model very similar to jj-mailbox. Key features that jj-mailbox can learn from:

- Task dependency graphs (`blocks`/`blockedBy`)
- Richer message types (idle, approval, shutdown)
- Quality gate hooks (reject task completion on test failure)

jj-mailbox already has advantages over Claude Code Teams (cross-machine via git,
agent-agnostic, full version history, jj conflict safety). These enhancements
add coordination capabilities while preserving those strengths.

## 1. Task Management with Dependency Graph

### Current state

`shared/tasks/` is a convention directory with no defined schema.

### Enhancement

Define a standard task schema and add CLI commands:

```json
// shared/tasks/task-001.json
{
  "id": "task-001",
  "subject": "Implement Slack adapter",
  "activeForm": "Implementing Slack adapter",
  "status": "pending",
  "assignee": null,
  "created_by": "lead",
  "created_at": "2026-03-13T10:00:00Z",
  "priority": 1,
  "blocks": [],
  "blockedBy": [],
  "metadata": {}
}
```

Task state transitions:

```
pending → in_progress → completed
            ↓
          blocked (when blockedBy contains incomplete tasks)
```

Claiming rules (consistent with Claude Code Teams):
- Agent finds tasks where status=pending and all blockedBy tasks are completed
- Claims highest priority (lowest number) task first
- Claim = set `assignee` to self + `status` to `in_progress`
- jj's concurrency safety ensures no conflicting claims (if conflict occurs, jj records it, agents check and retry)

New CLI commands:

```bash
jj-mailbox task create "Implement Slack adapter" --priority 1 --blocked-by task-000
jj-mailbox task claim                  # Auto-claim highest priority ready task
jj-mailbox task complete task-001      # Mark as completed
jj-mailbox task list                   # Show task board
```

## 2. Extended Message Types

### Current state

4 types: `message`, `task`, `reply`, `broadcast`.

### Enhancement

Add 4 new types for agent lifecycle management:

| New type | Purpose | Description |
|----------|---------|-------------|
| `idle` | Idle notification | Agent reports completion, available for new work |
| `approval_request` | Approval request | Agent requests lead/human review before proceeding |
| `approval_response` | Approval reply | Approve / reject with feedback |
| `shutdown` | Graceful shutdown | Lead signals agent to wind down |

Example — idle notification:

```json
{
  "version": "0.1",
  "id": "msg-idle-01",
  "timestamp": "2026-03-13T11:00:00Z",
  "from": "gsd",
  "to": "lead",
  "type": "idle",
  "subject": "Task completed, awaiting instructions",
  "body": "Completed task-001 (Slack adapter basic implementation). Ready for new work.",
  "refs": ["task-001"],
  "metadata": {
    "completed_tasks": ["task-001"],
    "available_capacity": true
  }
}
```

Example — approval request (plan mode):

```json
{
  "version": "0.1",
  "id": "msg-approval-01",
  "timestamp": "2026-03-13T11:05:00Z",
  "from": "gsd",
  "to": "lead",
  "type": "approval_request",
  "subject": "Feishu adapter design pending review",
  "body": "Design document at shared/artifacts/feishu-adapter-design.md",
  "refs": ["task-002"],
  "metadata": {
    "artifact_path": "shared/artifacts/feishu-adapter-design.md",
    "requires": "human_approval"
  }
}
```

**Backward compatible**: Agents that don't recognize new types can treat them as regular messages (just read `body`).

## 3. Agent Status Enhancement

### Current state

`agents/{name}/status.json` has 3 states: `online`, `busy`, `offline`.

### Enhancement

Add `idle` and `waiting_approval` states with richer context:

```json
{
  "status": "idle",
  "last_seen": "2026-03-13T11:00:00Z",
  "current_task": null,
  "completed_tasks": ["task-001"],
  "available_since": "2026-03-13T11:00:00Z",
  "capabilities": ["slack-adapter", "python", "web-search"]
}
```

Extended status values:

| Status | Meaning | Triggered when |
|--------|---------|----------------|
| `online` | Online, processing messages | Agent starts |
| `busy` | Busy, executing a task | After claiming a task |
| `idle` | Idle, awaiting instructions | After task completion (**new**) |
| `offline` | Offline | Agent exits |
| `waiting_approval` | Waiting for review | After sending approval_request (**new**) |

## 4. Quality Gate Hooks (TaskCompleted Validation)

### Inspiration

Claude Code Teams' TaskCompleted hook can return exit code 2 to reject task
completion and feed stderr back to the agent as feedback.

### Enhancement

Support hooks in `jj-mailbox task complete`:

```yaml
# config/hooks.yaml
on_task_complete:
  - name: "run-tests"
    command: "cd ${TASK_WORKSPACE} && make test"
    # exit 0 = pass, exit 2 = reject (feed stderr back to agent)

  - name: "lint-check"
    command: "cd ${TASK_WORKSPACE} && make lint"
```

Execution flow:

```
Agent: jj-mailbox task complete task-001
  → Run on_task_complete hooks from hooks.yaml
  → All hooks exit 0 → task marked completed
  → Any hook exits 2 → task stays in_progress, stderr sent as message to agent

# Auto-generated feedback message:
{
  "type": "reply",
  "from": "system",
  "to": "gsd",
  "subject": "Task task-001 completion rejected: tests failed",
  "body": "FAIL: test_slack_adapter.py::test_connection ...",
  "refs": ["task-001"]
}
```

The agent doesn't need to know about hooks — it just receives a message saying
"tests failed, please fix" and continues working.

## Comparison: jj-mailbox vs Claude Code Agent Teams

| Capability | Claude Code Teams | jj-mailbox |
|------------|------------------|------------|
| **Cross-machine** | Local only (`~/.claude/`) | Via git remote, cross-machine/region |
| **Cross-platform agents** | Claude Code only | Any file-aware agent (Claude/GPT/open-source) |
| **Message persistence** | Cleaned after completion (42 dirs, only 5 had files) | Fully preserved, complete audit history |
| **Concurrency safety** | `flock()` file locks | jj native conflict handling (more elegant) |
| **External platform integration** | None | Platform Bridge for Slack/Feishu/etc. |
| **Version control** | None | Every message has a jj commit, any point-in-time recoverable |

## Scope

```
Changed:
  + bin/jj-mailbox           — add `task` subcommand family (~150 lines bash)
  + spec/PROTOCOL.md         — extend message types and task schema
  + config/hooks.yaml        — quality gate hook configuration

Unchanged:
  = bin/jj-mailbox send/read/inbox — existing message commands
  = inbox/ directory structure
  = sync daemon
  = base message JSON schema (only metadata and type extensions)
```

## Validation

- Two agents collaborate on a multi-step task with dependencies
- Agent A creates tasks with blockedBy → Agent B claims and completes prerequisites → Agent A unblocks
- Quality hook rejects incomplete work → agent receives feedback and iterates

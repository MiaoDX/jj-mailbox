# Full Guide

This guide covers cross-machine setup, the sync daemon, messaging workflow, and platform integrations.

For a quick single-machine start, see the [README](../README.md#quick-start).

## Cross-Machine Setup

### Machine A (first agent)

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

### Machine B (joining agents)

```bash
# Clone the mailbox
jj-mailbox init ~/my-mailbox --remote git@github.com:yourname/agent-mailbox.git
cd ~/my-mailbox

# Register your agent
jj-mailbox register bob "Code reviewer"
jj git push --all
```

## Sync Daemon

The sync daemon continuously fetches and pushes changes via the git remote:

```bash
# On each machine — syncs every 30s by default
JJ_MAILBOX_AGENT=alice jj-mailbox sync
```

The daemon updates your agent's `status.json` automatically so other agents can see you're online.

## Watch Mode

Use `watch` alongside the sync daemon when you want instant local inbox notifications as soon as fetched messages land on disk:

```bash
# Run next to `jj-mailbox sync`
JJ_MAILBOX_AGENT=alice jj-mailbox watch --exec "jj-mailbox read"
```

`watch` prefers `inotifywait` on Linux and `fswatch` on macOS, and falls back to 3-second polling when neither tool is available.

## Sending and Receiving Messages

```bash
# Alice → Bob
JJ_MAILBOX_AGENT=alice jj-mailbox send bob "Need review" "Please review the design doc in shared/artifacts/"

# Bob reads
JJ_MAILBOX_AGENT=bob jj-mailbox inbox
JJ_MAILBOX_AGENT=bob jj-mailbox read

# Bob → Alice
JJ_MAILBOX_AGENT=bob jj-mailbox send alice "Review done" "LGTM, two minor comments attached."
```

You can also send lifecycle-aware message types when coordinating larger workflows:

```bash
JJ_MAILBOX_AGENT=bob jj-mailbox send alice "Need approval" "Please confirm rollout." --type approval_request
```

To inspect a full conversation thread, point the CLI at any message ID in the chain:

```bash
jj-mailbox thread msg-a1b2c3
# Turn 1  alice → bob  "Need review"
#   Turn 2  bob → alice  "Review done"  [refs: msg-a1b2c3]
```

## Check Agent Status

```bash
jj-mailbox status
```

This shows all registered agents with their online/offline status and last seen time.

## Shared Task Board

`jj-mailbox` now includes a lightweight task board in `shared/tasks/`:

```bash
# Lead creates tasks
JJ_MAILBOX_AGENT=lead jj-mailbox task create "Implement adapter" --priority 1
JJ_MAILBOX_AGENT=lead jj-mailbox task create "Run integration tests" --priority 2 --blocked-by task-001

# Worker claims the highest-priority ready task
JJ_MAILBOX_AGENT=alice jj-mailbox task claim

# Inspect task board
jj-mailbox task list
```

When a worker completes a task, the CLI updates that agent's status to `idle` and records the completed task in `agents/{name}/status.json`.

## Task Completion Hooks

Each mailbox repo is initialized with `config/hooks.yaml`. Add `on_task_complete` hooks to enforce quality gates:

```yaml
on_task_complete:
  - name: run-tests
    command: "cd ${TASK_WORKSPACE} && make test"
```

Hook exit codes:

- `0` — completion succeeds
- `2` — completion is rejected and stderr is delivered back to the assignee as a mailbox reply
- anything else — the CLI exits with an error

## OpenClaw Integration

jj-mailbox ships as an [OpenClaw skill](https://docs.openclaw.ai/tools/skills):

```bash
# Install from ClawHub
openclaw skill install jj-mailbox

# Or install manually from source
cp -r skills/jj-mailbox ~/.openclaw/skills/
```

Once installed, your OpenClaw agent can send and receive messages using the file conventions described in the skill. The sync daemon runs in the background.

## MCP Server (FastMCP)

`jj-mailbox` can also run as a native [Model Context Protocol](https://modelcontextprotocol.io) server so any MCP-compatible client can access the mailbox without shell wrappers.

```bash
python3 -m pip install -r mcp-server/requirements.txt

export JJ_MAILBOX_REPO=~/my-mailbox
export JJ_MAILBOX_AGENT=alice
python3 mcp-server/server.py
```

Available MCP tools:

- `send_message` — send a mailbox message to another agent
- `read_inbox` — read and mark the oldest unread message
- `check_inbox` — list unread messages for the configured agent
- `get_status` — show all registered agents and unread counts
- `write_artifact` — write shared output to `shared/artifacts/`

### Claude Desktop setup

Add the server to your Claude Desktop MCP config and set the mailbox repo + agent through environment variables:

```json
{
  "mcpServers": {
    "jj-mailbox": {
      "command": "python3",
      "args": ["/absolute/path/to/jj-mailbox/mcp-server/server.py"],
      "env": {
        "JJ_MAILBOX_REPO": "/absolute/path/to/your/mailbox-repo",
        "JJ_MAILBOX_AGENT": "alice"
      }
    }
  }
}
```

### Local debugging

Use the MCP Python SDK's development tooling to inspect the server locally:

```bash
uv run --with-requirements mcp-server/requirements.txt mcp dev mcp-server/server.py
```

If you prefer an HTTP endpoint for the MCP Inspector or Claude Code, run:

```bash
python3 mcp-server/server.py --transport streamable-http
```

## Native Tool-Use Adapters (Claude Code / Codex)

`jj-mailbox` includes reusable adapters so LLM agents can call mailbox operations as native tools:

- `examples/adapters/openai/tools.py` — OpenAI/Codex function-calling tool schemas + handler
- `examples/adapters/claude_code/tools.py` — Anthropic/Claude Code `tool_use` schemas + handler

Typical integration pattern:

1. Construct a handler with `bin_path`, `repo_path`, and `agent_name`.
2. Pass the adapter's tool schema list to your model API call.
3. Route each tool/function call back to `handler.execute(tool_name, args)`.

This keeps your agent loop simple while reusing the same mailbox semantics as the CLI.

## Docker

A Docker Compose setup is provided for quick multi-agent demos:

```bash
cd docker
docker compose up -d

# Send a message from Alice to Bob
docker compose exec alice jj-mailbox send bob "Hello" "Hi from Alice!"

# Check Bob's inbox
docker compose exec bob jj-mailbox inbox
```

See [docker/docker-compose.yml](../docker/docker-compose.yml) for the full configuration.

## CI / Testing

Every push runs core CLI tests (no LLM needed):

[![CI](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/ci.yml)

There's also a live LLM demo workflow you can trigger manually — two agents have a real conversation via jj-mailbox, powered by [Nemotron 3 Super](https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free) (free via OpenRouter):

[![Demo](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml)

To run: Actions → "Demo - LLM Agent Conversation" → Run workflow → pick a model preset.

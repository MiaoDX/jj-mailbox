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

## Check Agent Status

```bash
jj-mailbox status
```

This shows all registered agents with their online/offline status and last seen time.

## OpenClaw Integration

jj-mailbox ships as an [OpenClaw skill](https://docs.openclaw.ai/tools/skills):

```bash
# Install the skill
cp -r skills/jj-mailbox ~/.openclaw/skills/

# Or install from ClawHub (coming soon)
# openclaw skill install jj-mailbox
```

Once installed, your OpenClaw agent can send and receive messages using the file conventions described in the skill. The sync daemon runs in the background.

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

There's also a live LLM demo workflow you can trigger manually — two agents have a real conversation via jj-mailbox, powered by [MiMo-V2-Flash](https://github.com/XiaomiMiMo/MiMo-V2-Flash) (free via OpenRouter) or Kimi:

[![Demo](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml/badge.svg)](https://github.com/MiaoDX/jj-mailbox/actions/workflows/demo-llm.yml)

To run: Actions → "Demo - LLM Agent Conversation" → Run workflow → pick a model preset.

# LLM Conversation Demo

Two AI agents (Alice the API designer, Bob the code reviewer) have a real conversation via jj-mailbox using any OpenAI-compatible API.

## Setup

```bash
# 1. Initialize a mailbox repo
jj-mailbox init /tmp/demo
cd /tmp/demo
jj-mailbox register alice "API designer"
jj-mailbox register bob "Code reviewer"

# 2. Set your API key
export LLM_API_KEY="your-key"
export JJ_MAILBOX_REPO="/tmp/demo"

# 3. (Optional) Choose a model — defaults to MiMo-V2-Flash (free via OpenRouter)
export LLM_API_BASE="https://openrouter.ai/api/v1"
export LLM_MODEL="xiaomi/mimo-v2-flash:free"
```

## Run

```bash
# Default: 3 rounds of conversation about API design
python3 agent_chat.py

# Custom task and rounds
python3 agent_chat.py "Design a caching strategy for a web app" 5
```

## What Happens

1. Alice proposes an initial design
2. Bob reviews and gives feedback
3. They go back and forth for N rounds
4. Conversation log is saved to `shared/artifacts/conversation.json`

All messages are real JSON files in the jj-mailbox repo — you can inspect them with `jj-mailbox inbox` or browse the filesystem directly.

## CI Version

This same demo runs as a GitHub Actions workflow. See [.github/workflows/demo-llm.yml](../../.github/workflows/demo-llm.yml) — trigger it manually from the Actions tab.

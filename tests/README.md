# jj-mailbox Tests

| Test | Directory | LLM? | Secrets | CI |
|------|-----------|-------|---------|----|
| CLI protocol | (ci.yml) | No | None | auto |
| Scripted agents | scripted/ | No | None | auto |
| Adapter regression | adapters/ | No | None | auto |
| MCP wrapper | mcp/ | No | None | auto |
| smolagents | smolagents/ | Yes | LLM_API_KEY | auto if secret |
| LLM tool-calling | llm/ | Yes | LLM_API_KEY | auto if secret |
| Comparison | comparison/ | No | None | manual/weekly |
| OpenClaw | openclaw/ | Yes | LLM_API_KEY | auto if secret (Docker) |

All LLM tests use OpenRouter via `LLM_API_KEY`. One secret for everything.
See [docs/MODEL_CHOICES.md](../docs/MODEL_CHOICES.md) for provider details.

---

## CLI protocol (ci.yml)

Tests the raw protocol: init, register, send, inbox, read, bidirectional, status,
multi-agent broadcast, multi-turn threading with refs chain.

```bash
# Runs in CI automatically. See .github/workflows/ci.yml for steps.
```

---

## Scripted agents

Deterministic, no LLM, stdlib only. Tests refs chain and shared artifacts.

```bash
python3 tests/scripted/test.py
```

**Scenario:** 3-turn Planner → Researcher → Planner conversation.

---

## Adapter regression

Stdlib-only regression coverage for the reusable OpenAI/Codex and Claude Code
adapter modules.

```bash
python3 tests/adapters/test.py
```

**Scenario:** import both adapter modules, send/read a message via the shared
execution handler, and write an artifact without a live LLM.

---

## MCP wrapper

Stdlib-only regression coverage for the FastMCP server wrapper. The test injects
a fake `FastMCP` implementation so it can validate tool registration and CLI
dispatch without installing the MCP SDK.

```bash
python3 tests/mcp/test.py
```

**Scenario:** register the MCP tool set, send/read a message through the wrapper,
check status output, and verify artifact writes stay inside `shared/artifacts/`.

---

## smolagents

Uses the [smolagents](https://github.com/huggingface/smolagents) framework with jj-mailbox
CLI wrapped as `Tool` subclasses.

```bash
pip install -r tests/smolagents/requirements.txt
export LLM_API_KEY=sk-or-...
python3 tests/smolagents/test.py
```

**Scenario:** Alice sends Bob a caching design question, Bob reads and replies.

---

## LLM tool-calling

Uses OpenAI function calling directly. Any OpenAI-compatible provider works.

```bash
pip install openai
export LLM_API_KEY=sk-or-...
python3 tests/llm/test.py
```

**Scenario:** 3-round code review — Alice proposes, Bob reviews, Alice incorporates.

---

## Comparison benchmark

Runs the same 3-agent task with both an in-memory Slack simulation and real jj-mailbox,
then generates a `COMPARISON.md` report.

```bash
python3 tests/comparison/benchmark.py
```

---

## OpenClaw integration

Five OpenClaw agents in Docker, sharing one jj repo volume.

```bash
cd tests/openclaw

./test.sh --no-llm      # CLI-only, 30 messages, 5 agents
./test.sh --llm-smoke   # 1 real OpenClaw agent turn + verify
./test.sh               # both

# Or with explicit key:
LLM_API_KEY=sk-or-... ./test.sh
```

`.env` auto-loading: if `LLM_API_KEY` is not exported, `test.sh` sources `../../.env`.

---

## Running locally

```bash
chmod +x bin/jj-mailbox

# No-LLM tests (always work)
python3 tests/scripted/test.py
python3 tests/adapters/test.py
python3 tests/mcp/test.py
python3 tests/comparison/benchmark.py

# LLM tests (need LLM_API_KEY in .env or exported)
pip install openai 'smolagents[openai]'
python3 tests/llm/test.py
python3 tests/smolagents/test.py
```

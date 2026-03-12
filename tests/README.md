# jj-mailbox Testing Pyramid

Tests are organized in levels of increasing sophistication.

| Level | Directory | LLM? | Secrets | CI Trigger |
|-------|-----------|-------|---------|------------|
| 1 | (ci.yml) | No | None | auto, every push |
| 2a | level2a-scripted/ | No | None | auto, every push |
| 2b | level2b-smolagents/ | Free (HF) | HF_TOKEN | auto if secret |
| 3a | level3a-llm-free/ | Yes, free | LLM_API_KEY | auto if secret |
| 3b | level3b-llm-online/ | Yes, paid | LLM_API_KEY | manual only |
| 4 | level4-comparison/ | Simulated | None | manual/weekly |
| OC | openclaw/ | Yes | LLM_API_KEY | manual (Docker) |

All LLM tests are **model-pluggable** — any OpenAI-compatible provider works.
See [docs/MODEL_CHOICES.md](../docs/MODEL_CHOICES.md) for provider comparison.

---

## Level 1 — Bash CLI tests

**Workflow:** [`.github/workflows/ci.yml`](../.github/workflows/ci.yml)

Tests the raw protocol: init, register, send, inbox, read, bidirectional, status,
multi-agent broadcast, multi-turn threading with refs chain.

```bash
# No local setup needed — runs in CI automatically.
# To run manually, see individual test steps in ci.yml
```

---

## Level 2a — Python scripted agents

**Workflow:** [`.github/workflows/ci-level2a.yml`](../.github/workflows/ci-level2a.yml)

Deterministic, no LLM, stdlib only. Tests refs chain and shared artifacts.

```bash
# No pip install needed
python3 tests/level2a-scripted/test.py
```

**What's tested:**
- 3-turn conversation: Planner → Researcher → Planner
- `refs` field chains correctly across turns
- Messages move from `new/` to `processed/` after reading
- Shared artifact written to `shared/artifacts/`

---

## Level 2b — smolagents with tiny HF model

**Workflow:** [`.github/workflows/ci-level2b.yml`](../.github/workflows/ci-level2b.yml)

Uses `smolagents` + `Qwen/Qwen2.5-0.5B-Instruct` (free with HF_TOKEN). The jj-mailbox
CLI is wrapped as smolagents `Tool` subclasses so the LLM can call them.

```bash
pip install -r tests/level2b-smolagents/requirements.txt
export HF_TOKEN=hf_...
python3 tests/level2b-smolagents/test.py
```

Skips gracefully if `HF_TOKEN` is not set.

---

## Level 3a — Tool-calling LLM agent (free model)

**Workflow:** [`.github/workflows/ci-level3a.yml`](../.github/workflows/ci-level3a.yml)

Uses OpenAI function calling with a free model. Any provider works (see [docs/MODEL_CHOICES.md](../docs/MODEL_CHOICES.md)).

```bash
pip install openai

# Option A: local ollama
export OLLAMA=1  # auto-configures localhost:11434 + qwen2.5:0.5b

# Option B: OpenRouter (default, free)
export LLM_API_KEY=sk-or-...

# Option C: any provider
export LLM_API_KEY=gsk_... LLM_API_BASE=https://api.groq.com/openai/v1 LLM_MODEL=llama-3.3-70b-versatile

python3 tests/level3a-llm-free/test.py
```

Skips gracefully if `LLM_API_KEY` is not set and `OLLAMA` is not set.

**Scenario:** 3-round code review — Alice proposes a function, Bob reviews, Alice incorporates feedback.

---

## Level 3b — Tool-calling LLM agent (quality model)

**Workflow:** [`.github/workflows/ci-level3b.yml`](../.github/workflows/ci-level3b.yml) — manual trigger only

Same structure as 3a but uses Kimi (moonshot-v1-8k) by default and runs a more complex
3-agent (Planner + Researcher + Critic), 5-round scenario.

```bash
pip install openai
export LLM_API_KEY=sk-...
export LLM_API_BASE=https://api.moonshot.cn/v1
export LLM_MODEL=moonshot-v1-8k
python3 tests/level3b-llm-online/test.py
```

---

## Level 4 — Slack-style vs jj-mailbox comparison

**Workflow:** [`.github/workflows/ci-level4.yml`](../.github/workflows/ci-level4.yml) — manual / weekly

Runs the same 3-agent task with both an in-memory Slack simulation and real jj-mailbox,
then generates a `COMPARISON.md` report highlighting structural differences.

```bash
# No pip install, no secrets needed
python3 tests/level4-comparison/benchmark.py
cat tests/level4-comparison/COMPARISON.md
```

---

## OpenClaw integration test

**Directory:** `tests/openclaw/`

Five OpenClaw agents (alice, bob, carol, dave, eve) in Docker, sharing one jj repo volume.
Tests: OpenClaw agent → reads SKILL.md → uses jj-mailbox CLI → shared jj repo.

```bash
cd tests/openclaw

# CLI-only: 30 messages across 5 agents, no API key needed
./test.sh --no-llm

# LLM smoke: 1 real OpenClaw agent turn, verify mailbox receipt
./test.sh --llm-smoke

# Full: LLM smoke + 30-message CLI round-robin
./test.sh

# Explicit provider:
LLM_API_KEY=sk-or-... ./test.sh
```

Requires Docker. Builds on `ghcr.io/openclaw/openclaw:latest`.

**`.env` auto-loading:** If `LLM_API_KEY` is not in the environment, `test.sh` sources `../../.env` automatically.

**`--no-llm` mode:** 30 CLI messages in round-robin across 5 agents. No OpenClaw agent invocation.

**`--llm-smoke` mode:** Runs 1 real OpenClaw agent turn (alice → bob), verifies the mailbox received a message regardless of content. Falls back to CLI if the model doesn't use the skill.

---

## Running all auto levels locally

```bash
# Prerequisites: jj installed, git configured
chmod +x bin/jj-mailbox

# Level 1 (manual equivalent)
bin/jj-mailbox init /tmp/test && cd /tmp/test
# ... (see ci.yml for steps)

# Level 2a (no installs)
python3 tests/level2a-scripted/test.py

# Level 4 (no installs)
python3 tests/level4-comparison/benchmark.py
```

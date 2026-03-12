# Model Choices

jj-mailbox is **model-pluggable** — any OpenAI-compatible API works.
All tests and demos accept the same three environment variables:

```bash
LLM_API_KEY=...                          # your API key
LLM_API_BASE=https://openrouter.ai/api/v1  # provider endpoint
LLM_MODEL=openrouter/free                # model ID
```

## Recommended Providers (Free Tier)

| Provider | Base URL | Recommended Model | Daily Limit | Tool Calling | Signup |
|----------|----------|-------------------|-------------|:------------:|--------|
| **OpenRouter** | `https://openrouter.ai/api/v1` | `openrouter/free` | 50 req (1K with $10) | Yes | No card |
| **Groq** | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` | 1K req | Yes | No card |
| **Cerebras** | `https://api.cerebras.ai/v1` | `llama-3.3-70b` | 1M tokens | Yes | No card |
| **Google AI Studio** | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.5-flash` | 250 req | Yes | No card |

### OpenRouter (default)

The best starting point. The `openrouter/free` meta-model auto-routes to whichever free model supports your request (including tool calling). ~27 free models available including Qwen3, GPT-OSS, Llama 4, DeepSeek R1.

```bash
# Sign up at https://openrouter.ai/ — no credit card needed
LLM_API_KEY=sk-or-...
LLM_API_BASE=https://openrouter.ai/api/v1
LLM_MODEL=openrouter/free
```

Free tier: 20 RPM, 50 req/day. One-time $10 purchase unlocks 1K req/day permanently.

Browse free models: https://openrouter.ai/collections/free-models

### Groq

Fastest inference (~300 tok/s on LPU hardware). Llama 3.3 70B is strong at tool calling.

```bash
# Sign up at https://console.groq.com/ — no credit card needed
LLM_API_KEY=gsk_...
LLM_API_BASE=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.3-70b-versatile
```

Free tier: 30 RPM, 1K req/day, 12K TPM.

### Cerebras

Most generous free limits. ~20x faster than GPU inference on wafer-scale hardware.

```bash
# Sign up at https://cloud.cerebras.ai/ — no credit card needed
LLM_API_KEY=csk-...
LLM_API_BASE=https://api.cerebras.ai/v1
LLM_MODEL=llama-3.3-70b
```

Free tier: 30 RPM, 1M tokens/day, 14.4K req/day. Context limited to 8K on free tier.

### Google AI Studio

Highest model quality among free providers. Gemini 2.5 Flash rivals frontier models.

```bash
# Get API key at https://aistudio.google.com/apikey — no credit card needed
LLM_API_KEY=AIza...
LLM_API_BASE=https://generativelanguage.googleapis.com/v1beta/openai/
LLM_MODEL=gemini-2.5-flash
```

Free tier: 10 RPM, 250 req/day.

### Local (Ollama)

Zero cost, fully offline. Needs a machine with enough RAM for the model.

```bash
# Install: https://ollama.ai/ then: ollama pull qwen2.5:7b
LLM_API_KEY=ollama
LLM_API_BASE=http://localhost:11434/v1
LLM_MODEL=qwen2.5:7b
OLLAMA=1
```

## Switching Providers

All providers use the same OpenAI-compatible interface, so switching is just env vars:

```bash
# Run any test with any provider
LLM_API_KEY=gsk_... LLM_API_BASE=https://api.groq.com/openai/v1 LLM_MODEL=llama-3.3-70b-versatile \
  python3 tests/level3a-llm-free/test.py
```

The same applies to the OpenClaw integration test, CI workflows, and demos.

## HF_TOKEN (Level 2b only)

Level 2b uses [smolagents](https://github.com/huggingface/smolagents) which requires a Hugging Face token — separate from `LLM_API_KEY`. Get one free at https://hf.co/settings/tokens.

## For CI

Add secrets to your GitHub repo settings (`Settings → Secrets → Actions`):

| Secret | Used by | Required? |
|--------|---------|-----------|
| `LLM_API_KEY` | Level 3a, 3b, OpenClaw test | For LLM tests |
| `HF_TOKEN` | Level 2b | For smolagents test |

One key covers all LLM-based tests. Set `LLM_API_BASE` and `LLM_MODEL` in the workflow if you want a specific provider (defaults to OpenRouter).

---

<!-- Sponsors -->

## Sponsors

_This section is reserved for providers and organizations supporting jj-mailbox development and CI infrastructure._

_Interested in sponsoring? See [CONTRIBUTING.md](../CONTRIBUTING.md)._

<!--
Sponsor tiers:
- Provide free API credits for CI → logo + link here
- Maintain a free model tier used by our tests → mention here
-->

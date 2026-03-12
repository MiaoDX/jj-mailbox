# Model Choices

jj-mailbox uses **OpenRouter** for all LLM tests. One API key, one provider.

```bash
LLM_API_KEY=sk-or-...                      # OpenRouter API key
LLM_API_BASE=https://openrouter.ai/api/v1  # (default, can omit)
LLM_MODEL=openrouter/auto                  # (default, can omit)
```

## OpenRouter

Sign up at https://openrouter.ai/ — no credit card needed.

The `openrouter/auto` meta-model auto-routes to the best available model for your request
(including tool calling). ~27 free models available including Qwen3, GPT-OSS, Llama 4,
DeepSeek R1.

- Free tier: 20 RPM, 50 req/day
- One-time $10 purchase: 1K req/day permanently
- Browse free models: https://openrouter.ai/collections/free-models

## Setup

```bash
# 1. Get your key at https://openrouter.ai/settings/keys
# 2. Add to .env at project root:
echo 'LLM_API_KEY=sk-or-...' >> .env

# 3. Run any LLM test:
python3 tests/llm/test.py
python3 tests/smolagents/test.py
```

## For CI

Add one secret to GitHub repo settings (`Settings → Secrets → Actions`):

| Secret | Used by |
|--------|---------|
| `LLM_API_KEY` | smolagents, llm, OpenClaw tests |

That's it. One key covers everything.

## Other Providers

The codebase uses the OpenAI-compatible API format, so other providers could work
by overriding `LLM_API_BASE` and `LLM_MODEL`. See GitHub issues for tracking:

- Groq, Cerebras, Google AI Studio, Ollama — tracked as future enhancements

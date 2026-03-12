# docs/

## Guides

| File | What |
|------|------|
| [GUIDE.md](GUIDE.md) | Cross-machine setup, sync daemon, OpenClaw integration |
| [WHY-JJ.md](WHY-JJ.md) | Why jj over plain git, design principles |
| [CONTEXT.md](CONTEXT.md) | Project background and motivation |
| [RESEARCH.md](RESEARCH.md) | Research notes and references |
| [MODEL_CHOICES.md](MODEL_CHOICES.md) | LLM model selection for CI testing |

## Figures

Terminal screenshots used in the top-level README. Generated from **live test runs and CLI output** — not hardcoded.

| File | Format | Source |
|------|--------|--------|
| [fig/test-suite.svg](fig/test-suite.svg) | static | `tests/run_all.py --no-llm` |
| [fig/agent-conversation.svg](fig/agent-conversation.svg) | static | `tests/scripted/test.py` |
| [fig/agent-conversation.gif](fig/agent-conversation.gif) | animated | `tests/scripted/test.py` |
| [fig/mailbox-status.svg](fig/mailbox-status.svg) | static | `jj-mailbox status/inbox/read` in temp repo |
| [fig/mailbox-status.gif](fig/mailbox-status.gif) | animated | same |

### Regenerating figures

When tests, CLI output format, or protocol change:

```bash
uv run python docs/generate_figs.py
```

The script (`generate_figs.py`) does three things:

1. **Captures real output** — runs the test suite, the scripted agent test, and sets up a temp mailbox repo to run CLI commands
2. **Colorizes** — parses lines for prompts, PASS/FAIL, agent names, JSON keys, message IDs, etc. (Catppuccin Mocha palette)
3. **Renders** — SVGs via string templates, GIFs via Pillow with macOS-style terminal chrome

Falls back to cached content if jj isn't installed or tests fail.

# Contributing to jj-mailbox

Thank you for your interest in contributing. jj-mailbox is a small project with a
specific purpose — Maildir for AI agents, version-controlled message passing powered
by jj — and every contribution, regardless of size, helps move that purpose forward.

Whether you have twenty minutes or twenty hours, there is a meaningful way to get
involved. This document explains how.

---

## Ways to Contribute

You do not need to write code to make a meaningful contribution.

- **Bug reports** — if something breaks, open an issue. A clear reproduction step is
  worth more than a half-finished patch.
- **Documentation** — improve the guides, fix a typo, add a missing example, clarify
  an ambiguous sentence.
- **Examples** — show a real use case: a new agent framework, a novel multi-agent
  pattern, a workflow that surprised you.
- **Testing** — try the project on an unusual platform or configuration, and report
  what you find.
- **Translations** — if you can make the docs accessible to a wider audience, that is
  genuinely valuable.
- **Design feedback** — review a proposal in `proposals/`, comment on an open issue, push
  back on a direction you think is wrong. Constructive disagreement is welcome.
- **Code** — new features, bug fixes, performance improvements, refactors.

---

## AI-Assisted Contributions Welcome

This project is about AI agent coordination. It is entirely fitting — and explicitly
encouraged — that AI coding agents help build it.

PRs authored with Claude Code, Codex, Gemini, OpenCode, OpenClaw, or any other AI
coding agent are welcome. You do not need to hide or apologize for AI assistance;
this project treats it as a normal part of the development workflow.

**Practical tips for AI-assisted contributions:**

- Include your agent in the commit trailer so the history stays honest:
  ```
  Co-Authored-By: Claude <noreply@anthropic.com>
  ```
- Review the diff before opening the PR. AI agents occasionally introduce
  unnecessary changes; a clean, focused diff is easier to review and more likely
  to be merged quickly.
- Make sure the agent runs the tests locally before you push. The test suite is
  fast and the bar for passing Level 1 is low.
- If the agent made a design decision you are not sure about, call it out in the PR
  description. It is easier to discuss a specific choice than to audit an entire diff.

---

## Development Setup

**Prerequisites**

- [jj](https://jj-vcs.dev/docs/install/) — the version-control system the project is
  built on. Version 0.21 or newer is recommended.
- `git` — used by jj as the storage backend.
- `bash` — required for the core CLI and most tests.
- `python3` — required for the scripted and LLM test levels (stdlib only for Level 2a;
  `pip` packages for LLM levels).
- Docker — required only for Level 5 (OpenClaw integration tests).

**Clone and set up**

```bash
git clone https://github.com/MiaoDX/jj-mailbox.git
cd jj-mailbox
export PATH="$PWD/bin:$PATH"
```

That is all. There are no compiled artefacts and no mandatory build step.

**Verify your setup**

```bash
bash examples/two-agents-demo/run.sh
```

If this completes without errors, your environment is ready.

---

## Running the Tests

jj-mailbox has five levels of tests, matching the five integration layers of the
project. You do not need to run all levels to contribute — Level 1 is the baseline
and it has no external dependencies.

### Level 1 — Core CLI (no API key required)

Tests the raw protocol: `init`, `register`, `send`, `inbox`, `read`, `status`,
bidirectional messaging, broadcast, and multi-turn threading with refs chain
verification.

```bash
cd tests && bash run_tests.sh
```

This is the fastest check and runs in CI on every push. If you change anything in
`bin/` or `spec/`, this level must pass before opening a PR.

### Level 2a — Scripted agent conversation (no API key required)

Deterministic, no LLM, uses only Python stdlib. Tests a 3-turn Planner → Researcher
→ Planner conversation including refs chain and shared artefacts.

```bash
python3 tests/scripted/test.py
```

### Level 2b — smolagents integration (LLM API key required)

Uses the [smolagents](https://github.com/huggingface/smolagents) framework with
jj-mailbox CLI wrapped as `Tool` subclasses.

```bash
pip install -r tests/smolagents/requirements.txt
export LLM_API_KEY=sk-or-...
python3 tests/smolagents/test.py
```

### Level 3a — OpenAI function-calling (LLM API key required)

Uses OpenAI-compatible function calling directly. Any OpenAI-compatible provider
works (the project uses OpenRouter by default).

```bash
pip install openai
export LLM_API_KEY=sk-or-...
python3 tests/llm/test.py
```

### Level 4 — Comparison benchmark (no API key required)

Runs the same 3-agent task with both an in-memory Slack simulation and real
jj-mailbox, then generates a `COMPARISON.md` report. Useful for catching regressions
in protocol semantics.

```bash
python3 tests/comparison/benchmark.py
```

### Level 5 — OpenClaw Docker integration (Docker required)

Five OpenClaw agents in Docker, sharing one jj repo volume. This is the heaviest
test and is only required when changing the OpenClaw integration.

```bash
cd tests/openclaw
./test.sh --no-llm      # CLI-only, 30 messages, 5 agents — no API key
./test.sh --llm-smoke   # 1 real OpenClaw agent turn + verify
./test.sh               # both
```

**LLM API key for Levels 2b, 3a, 5:** set `LLM_API_KEY` in your environment or in a
`.env` file at the repo root. The test scripts source it automatically.

See [tests/README.md](tests/README.md) and [docs/MODEL_CHOICES.md](docs/MODEL_CHOICES.md)
for provider details.

---

## Issue Labels

When browsing [open issues](https://github.com/MiaoDX/jj-mailbox/issues), the labels
help you find work that fits your situation.

| Label | Meaning |
|-------|---------|
| `good first issue` | Self-contained, well-scoped, does not require deep context |
| `size: small` | Expected to take less than a few hours |
| `help wanted` | External contributions are actively welcome here |
| `area: cli` | Changes to `bin/jj-mailbox` or the shell interface |
| `protocol` | Changes to the message format or sync protocol (`spec/`) |
| `area: tests` | Improvements to the test suite |
| `area: docs` | Documentation, guides, examples |
| `area: integrations` | Agent framework integrations (smolagents, OpenClaw, etc.) |
| `area: ci` | CI workflows and automation |

**Best starting points:** issues labelled both `good first issue` and `size: small`.
If you find an issue you want to work on, leave a comment before you start — it
avoids duplicate effort and lets a maintainer flag any context that would save you
time.

---

## Code Style

**Shell scripts**

- Always start with `set -euo pipefail`.
- Quote all variable expansions: `"$var"`, `"${array[@]}"`.
- Use `local` for variables inside functions.
- Prefer explicit error messages over silent failures.

**JSON**

- 2-space indentation.
- Follow the schema defined in [spec/PROTOCOL.md](spec/PROTOCOL.md).
- Keep message files minimal — do not add fields the spec does not define.

**Python**

- Standard library only for no-API-key tests (Levels 2a, 4).
- Explicit imports, no wildcard `from x import *`.
- No third-party dependencies without a corresponding `requirements.txt` entry.

---

## Pull Request Process

1. **Fork** the repository and create a branch from `main`. Use a descriptive branch
   name: `fix/inbox-empty-check`, `feat/zsh-completion`, `docs/setup-guide`.

2. **Make your changes.** Keep commits atomic and their messages clear. If you are
   fixing a bug, reference the issue number in the commit message.

3. **Run the tests.** At minimum, Level 1 must pass:
   ```bash
   cd tests && bash run_tests.sh
   ```
   If your change touches the scripted agents or LLM layers, run the appropriate
   level too.

4. **Open a PR** with a description that covers:
   - What changed and why.
   - Which test levels you ran and whether they passed.
   - Any design decisions you made that a reviewer should know about.

5. A maintainer will review the PR. Small, focused PRs with passing tests are
   reviewed fastest. If your PR sits without feedback for more than a week, leave a
   comment to ping for a review.

---

## Questions and Discussion

If you are unsure whether an idea is in scope, open an issue and describe what you
have in mind before writing code. It is a much better use of your time than building
something that does not fit the project direction.

The [issues page](https://github.com/MiaoDX/jj-mailbox/issues) is the right place
for bug reports, feature requests, and design discussions. There is no separate forum
or chat.

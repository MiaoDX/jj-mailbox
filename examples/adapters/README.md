# Native LLM adapters

These adapters expose `jj-mailbox` tools directly to LLM tool-calling APIs, so agents can call mailbox actions natively without shell wrappers in prompts.

## OpenAI / Codex

Use `examples.adapters.openai.tools.OPENAI_TOOLS` as your `tools` payload and call `JjMailboxOpenAITools.execute()` for tool execution.

## Claude Code / Anthropic

Use `examples.adapters.claude_code.tools.CLAUDE_TOOLS` as your Anthropic `tools` payload and call `JjMailboxClaudeTools.execute()` for `tool_use` handling.

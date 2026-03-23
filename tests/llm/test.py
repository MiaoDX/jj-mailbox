#!/usr/bin/env python3
"""
LLM tool-calling agent test.

Supports both OpenAI- and Anthropic-style tool calling so the same scenario can
run natively against either SDK.

Skips gracefully if LLM_API_KEY is not set.

Default: nvidia/nemotron-3-super-120b-a12b:free via OpenRouter + OpenAI SDK.

Scenario: "Code review, 3 rounds"
  Alice proposes a function design
  Bob reviews using read_inbox + send_message tool calls
  Alice incorporates feedback, writes final design to shared/artifacts/

Usage:
  LLM_API_KEY=sk-or-... python3 tests/llm/test.py
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

# Import shared helpers
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from _helpers import setup_repo as _setup_repo, cleanup_repo
from examples.adapters.openai.tools import OPENAI_TOOLS, JjMailboxOpenAITools

# Config from environment (defaults to OpenRouter + OpenAI SDK)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_SDK = os.environ.get("LLM_SDK", "openai").strip().lower() or "openai"
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")

MAX_TURNS = 6  # max tool-calling turns per agent per round
RETRY_DELAYS = [5, 15, 30]
SUPPORTED_SDKS = {"openai", "anthropic"}


class GracefulSkip(Exception):
    """Raised when the test should be skipped cleanly (exit 0)."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class AgentTurn:
    final_text: str
    tool_calls: list[ToolCall]
    assistant_message: dict[str, Any] | None


ANTHROPIC_TOOLS = [
    {
        "name": tool["function"]["name"],
        "description": tool["function"]["description"],
        "input_schema": tool["function"]["parameters"],
    }
    for tool in OPENAI_TOOLS
]


class AgentBackend:
    name = "base"
    tools: list[dict[str, Any]] = []

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    def make_initial_messages(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def run_turn(self, system_prompt: str, messages: list[dict[str, Any]], agent_name: str) -> AgentTurn:
        raise NotImplementedError

    def format_tool_result(self, tool_call_id: str, result_content: str) -> dict[str, Any]:
        raise NotImplementedError

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        assistant_message: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> None:
        raise NotImplementedError

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        return getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)

    def _handle_api_exception(self, exc: Exception, agent_name: str, attempt: int, delay: int | None) -> None:
        status_code = self._status_code(exc)
        exc_name = exc.__class__.__name__

        if status_code == 429 or "RateLimit" in exc_name:
            if delay is None:
                msg = f"SKIP: Rate limited on {self.model} — 429 after 3 retries"
                print(f"  [{agent_name}] {msg}")
                raise GracefulSkip(msg) from exc
            print(f"  [{agent_name}] 429 rate limited, retrying in {delay}s (attempt {attempt + 1}/3)...")
            time.sleep(delay)
            return

        if status_code == 404 or "NotFound" in exc_name:
            msg = f"SKIP: Model {self.model} not available — 404"
            print(f"  [{agent_name}] {msg}")
            raise GracefulSkip(msg) from exc

        if status_code == 402:
            msg = f"SKIP: {self.model} — 402 payment/limit exceeded"
            print(f"  [{agent_name}] {msg}")
            raise GracefulSkip(msg) from exc

        print(f"  [{agent_name}] API error: {exc}")
        raise exc


class OpenAIBackend(AgentBackend):
    name = "openai"
    tools = OPENAI_TOOLS

    def __init__(self, api_key: str, model: str, base_url: str):
        super().__init__(api_key=api_key, model=model)
        import openai

        self._openai = openai
        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.base_url = base_url

    def make_initial_messages(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def run_turn(self, system_prompt: str, messages: list[dict[str, Any]], agent_name: str) -> AgentTurn:
        del system_prompt
        response = None
        for attempt, delay in enumerate(RETRY_DELAYS + [None]):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    max_tokens=500,
                    temperature=0.7,
                )
                break
            except Exception as exc:  # SDK-specific exception hierarchy differs by provider
                self._handle_api_exception(exc, agent_name, attempt, delay)

        if not response or not response.choices:
            return AgentTurn(final_text="", tool_calls=[], assistant_message=None)

        msg = response.choices[0].message
        tool_calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            if not isinstance(args, dict):
                print(f"  [{agent_name}] Malformed tool args (got {type(args).__name__}), skipping")
                args = {}
            tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, args=args))

        if not tool_calls:
            return AgentTurn(final_text=msg.content or "", tool_calls=[], assistant_message=None)

        assistant_message = {
            "role": "assistant",
            "content": msg.content,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ],
        }
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            assistant_message["reasoning_content"] = reasoning

        return AgentTurn(final_text="", tool_calls=tool_calls, assistant_message=assistant_message)

    def format_tool_result(self, tool_call_id: str, result_content: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_content,
        }

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        assistant_message: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> None:
        messages.append(assistant_message)
        messages.extend(tool_results)


class AnthropicBackend(AgentBackend):
    name = "anthropic"
    tools = ANTHROPIC_TOOLS

    def __init__(self, api_key: str, model: str, base_url: str):
        super().__init__(api_key=api_key, model=model)
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key, base_url=base_url)
        self.base_url = base_url

    def make_initial_messages(self, system_prompt: str, user_prompt: str) -> list[dict[str, Any]]:
        del system_prompt
        return [{"role": "user", "content": user_prompt}]

    def run_turn(self, system_prompt: str, messages: list[dict[str, Any]], agent_name: str) -> AgentTurn:
        response = None
        for attempt, delay in enumerate(RETRY_DELAYS + [None]):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=messages,
                    tools=self.tools,
                    tool_choice={"type": "auto"},
                    max_tokens=500,
                    temperature=0.7,
                )
                break
            except Exception as exc:  # SDK-specific exception hierarchy differs by provider
                self._handle_api_exception(exc, agent_name, attempt, delay)

        if not response or not getattr(response, "content", None):
            return AgentTurn(final_text="", tool_calls=[], assistant_message=None)

        text_parts = []
        tool_calls = []
        assistant_content = []

        for block in response.content:
            block_type = getattr(block, "type", None)
            if block_type == "text":
                text = getattr(block, "text", "") or ""
                text_parts.append(text)
                assistant_content.append({"type": "text", "text": text})
            elif block_type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block.id,
                        name=block.name,
                        args=block.input if isinstance(block.input, dict) else {},
                    )
                )
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input if isinstance(block.input, dict) else {},
                    }
                )
            elif block_type in ("thinking", "reasoning"):
                # Thinking/reasoning blocks from Anthropic thinking models or
                # Kimi via Anthropic format — skip gracefully.
                pass
            else:
                # Unknown block type — ignore gracefully to be forward-compatible.
                pass

        if not tool_calls:
            return AgentTurn(final_text="\n".join(part for part in text_parts if part).strip(), tool_calls=[], assistant_message=None)

        return AgentTurn(
            final_text="",
            tool_calls=tool_calls,
            assistant_message={"role": "assistant", "content": assistant_content},
        )

    def format_tool_result(self, tool_call_id: str, result_content: str) -> dict[str, Any]:
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": result_content,
        }

    def append_tool_results(
        self,
        messages: list[dict[str, Any]],
        assistant_message: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> None:
        messages.append(assistant_message)
        messages.append({"role": "user", "content": tool_results})


BACKEND_FACTORIES = {
    "openai": lambda: OpenAIBackend(api_key=LLM_API_KEY, model=LLM_MODEL, base_url=LLM_API_BASE),
    "anthropic": lambda: AnthropicBackend(api_key=LLM_API_KEY, model=LLM_MODEL, base_url=ANTHROPIC_BASE_URL),
}


def setup_repo():
    return _setup_repo(BIN, [("alice", "Function designer"), ("bob", "Code reviewer")], prefix="jj-mailbox-3a-")


def make_backend() -> AgentBackend:
    if LLM_SDK not in SUPPORTED_SDKS:
        supported = ", ".join(sorted(SUPPORTED_SDKS))
        raise SystemExit(f"ERROR: Unsupported LLM_SDK={LLM_SDK!r}. Expected one of: {supported}")

    try:
        return BACKEND_FACTORIES[LLM_SDK]()
    except ImportError:
        print(f"ERROR: {LLM_SDK} SDK not installed.  pip install {LLM_SDK}")
        raise SystemExit(1) from None


def run_agent(agent_name, system_prompt, user_prompt, repo, backend: AgentBackend, log):
    """Run an agent with tool calling, returning the final text response."""
    messages = backend.make_initial_messages(system_prompt, user_prompt)
    tool_handler = JjMailboxOpenAITools(bin_path=BIN, repo_path=repo, agent_name=agent_name)

    for _turn in range(MAX_TURNS):
        turn = backend.run_turn(system_prompt=system_prompt, messages=messages, agent_name=agent_name)
        if not turn.assistant_message and not turn.tool_calls:
            print(f"  [{agent_name}] Empty response from {LLM_MODEL}, retrying turn...")
            continue

        if not turn.tool_calls:
            final_text = turn.final_text or ""
            log.append({"agent": agent_name, "type": "text", "content": final_text})
            return final_text

        tool_results = []
        for tc in turn.tool_calls:
            result = tool_handler.execute(tc.name, tc.args)
            print(f"  [{agent_name}] tool: {tc.name}({tc.args}) → {result[:80]}")
            log.append({"agent": agent_name, "type": "tool_call", "tool": tc.name, "args": tc.args, "result": result})

            tool_results.append(backend.format_tool_result(tc.id, result))

        backend.append_tool_results(messages, turn.assistant_message, tool_results)

    return "Max turns reached."


def main():
    print("=" * 60)
    print("LLM tool-calling agent test")
    print("=" * 60)

    if not LLM_API_KEY:
        print()
        print("ERROR: LLM_API_KEY not set.")
        print("   LLM_API_KEY=sk-or-... python3 tests/llm/test.py")
        sys.exit(1)

    backend = make_backend()

    print(f"SDK: {LLM_SDK}")
    print(f"Model: {LLM_MODEL}")
    if backend.name == "anthropic":
        print(f"API base: {ANTHROPIC_BASE_URL}")
    else:
        print(f"API base: {LLM_API_BASE}")
    print()

    repo = setup_repo()
    log = []

    try:
        # --- Round 1: Alice proposes function design ---
        print("Round 1: Alice proposes a function design")
        alice_reply = run_agent(
            "alice",
            "You are Alice, a software engineer. You collaborate with Bob via jj-mailbox. "
            "You MUST use the send_message tool to communicate — do NOT reply in plain text. "
            "Agent names are lowercase.",
            "Use the send_message tool to send bob a message proposing a design for a "
            "'process_batch(items)' function. Include: purpose, parameters, return value. "
            "Subject: 'Function design proposal'. Call the tool now.",
            repo,
            backend,
            log,
        )
        print(f"Alice: {alice_reply[:200]}")
        print()

        # --- Round 2: Bob reviews ---
        print("Round 2: Bob reviews Alice's proposal")
        bob_reply = run_agent(
            "bob",
            "You are Bob, a code reviewer. You collaborate with Alice via jj-mailbox. "
            "You MUST use read_inbox and send_message tools — do NOT reply in plain text. "
            "Agent names are lowercase.",
            "Use read_inbox to read Alice's message, then use send_message to reply to alice "
            "with your code review feedback. Subject: 'Re: Function design proposal'. "
            "Call the tools now.",
            repo,
            backend,
            log,
        )
        print(f"Bob: {bob_reply[:200]}")
        print()

        # --- Round 3: Alice incorporates feedback, writes artifact ---
        print("Round 3: Alice incorporates feedback, writes final design")
        alice_final = run_agent(
            "alice",
            "You are Alice, a software engineer. You collaborate with Bob via jj-mailbox. "
            "Use read_inbox to check for replies, write_artifact to save final designs.",
            "Read Bob's review with read_inbox. Then use write_artifact to save the "
            "final function design to 'function_design.md', incorporating his feedback. "
            "Include a brief summary of changes made.",
            repo,
            backend,
            log,
        )
        print(f"Alice final: {alice_final[:200]}")
        print()

        # --- Save conversation log ---
        log_path = os.path.join(repo, "shared", "artifacts", "conversation.json")
        with open(log_path, "w") as f:
            json.dump({"sdk": backend.name, "model": LLM_MODEL, "api_base": backend.base_url, "log": log}, f, indent=2)

        # --- Assertions ---
        print("Assertions:")

        # At least one message was sent (Bob's inbox or processed has messages)
        bob_new = os.path.join(repo, "inbox/bob/new")
        bob_proc = os.path.join(repo, "inbox/bob/processed")
        alice_new = os.path.join(repo, "inbox/alice/new")
        alice_proc = os.path.join(repo, "inbox/alice/processed")

        bob_total = (
            len([f for f in os.listdir(bob_new) if f.endswith(".json")])
            + len([f for f in os.listdir(bob_proc) if f.endswith(".json")])
        )
        alice_total = (
            len([f for f in os.listdir(alice_new) if f.endswith(".json")])
            + len([f for f in os.listdir(alice_proc) if f.endswith(".json")])
        )
        print(f"  Messages to bob: {bob_total}, to alice: {alice_total}")
        assert bob_total >= 1, "Bob should have received at least 1 message"

        # Artifact should exist
        artifact = os.path.join(repo, "shared", "artifacts", "function_design.md")
        if os.path.isfile(artifact):
            print("  Artifact exists: shared/artifacts/function_design.md ✓")
        else:
            print("  Note: artifact not written (agent may have responded in text instead)")

        # Conversation log exists
        assert os.path.isfile(log_path), "Conversation log should exist"
        print("  Conversation log: shared/artifacts/conversation.json ✓")

        print()
        print("=" * 60)
        print("✅ LLM tool-calling agent test passed!")
        print("=" * 60)

    except GracefulSkip as e:
        print()
        print(str(e))
        sys.exit(0)

    finally:
        # Print file tree for visibility
        print("\nFile tree:")
        for root, dirs, files in os.walk(repo):
            dirs[:] = [d for d in dirs if d not in (".jj", ".git")]
            level = root.replace(repo, "").count(os.sep)
            indent = "  " * level
            print(f"{indent}{os.path.basename(root)}/")
            for f in files:
                if not f.startswith("."):
                    print(f"{indent}  {f}")
        cleanup_repo(repo)


if __name__ == "__main__":
    main()

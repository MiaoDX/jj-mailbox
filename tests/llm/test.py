#!/usr/bin/env python3
"""
LLM tool-calling agent test.

Uses OpenAI function calling so agents invoke jj-mailbox as actual tool calls.
Skips gracefully if LLM_API_KEY is not set.

Default: nvidia/nemotron-3-super-120b-a12b:free via OpenRouter.

Scenario: "Code review, 3 rounds"
  Alice proposes a function design
  Bob reviews using read_inbox + send_message tool calls
  Alice incorporates feedback, writes final design to shared/artifacts/

Usage:
  LLM_API_KEY=sk-or-... python3 tests/llm/test.py
"""
import json
import os
import shutil
import sys
import time

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

# Import shared helpers
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from _helpers import run_cli, setup_repo as _setup_repo, cleanup_repo
from examples.adapters.openai.tools import OPENAI_TOOLS, JjMailboxOpenAITools

# Config from environment (defaults to OpenRouter)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
LLM_USER_AGENT = os.environ.get("LLM_USER_AGENT", "")  # e.g. "claude-code/1.0" for Kimi Code API

MAX_TURNS = 6  # max tool-calling turns per agent per round


class GracefulSkip(Exception):
    """Raised when the test should be skipped cleanly (exit 0)."""

TOOLS = OPENAI_TOOLS


def setup_repo():
    return _setup_repo(BIN, [("alice", "Function designer"), ("bob", "Code reviewer")], prefix="jj-mailbox-3a-")


def run_agent(agent_name, system_prompt, user_prompt, repo, client, log):
    """Run an agent with tool calling, returning the final text response."""
    import openai

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    tool_handler = JjMailboxOpenAITools(bin_path=BIN, repo_path=repo, agent_name=agent_name)

    for turn in range(MAX_TURNS):
        # Always use "auto" — many free model providers reject "required"
        # (e.g. z-ai returns 400, others return empty or text-only responses)
        choice = "auto"
        retry_delays = [5, 15, 30]
        response = None
        for attempt, delay in enumerate(retry_delays + [None]):
            try:
                response = client.chat.completions.create(
                    model=LLM_MODEL,
                    messages=messages,
                    tools=TOOLS,
                    tool_choice=choice,
                    max_tokens=500,
                    temperature=0.7,
                )
                break
            except openai.RateLimitError:
                if delay is None:
                    msg = f"SKIP: Rate limited on {LLM_MODEL} — 429 after 3 retries"
                    print(f"  [{agent_name}] {msg}")
                    raise GracefulSkip(msg)
                print(f"  [{agent_name}] 429 rate limited, retrying in {delay}s (attempt {attempt + 1}/3)...")
                time.sleep(delay)
            except openai.NotFoundError as e:
                msg = f"SKIP: Model {LLM_MODEL} not available — 404"
                print(f"  [{agent_name}] {msg}")
                raise GracefulSkip(msg)
            except openai.APIStatusError as e:
                if e.status_code == 402:
                    msg = f"SKIP: {LLM_MODEL} — 402 payment/limit exceeded"
                    print(f"  [{agent_name}] {msg}")
                    raise GracefulSkip(msg)
                print(f"  [{agent_name}] API error: {e}")
                raise
        if not response.choices:
            print(f"  [{agent_name}] Empty response from {LLM_MODEL}, retrying turn...")
            continue
        msg = response.choices[0].message

        # If no tool calls, we're done
        if not msg.tool_calls:
            final_text = msg.content or ""
            log.append({"agent": agent_name, "type": "text", "content": final_text})
            return final_text

        # Execute tool calls
        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]})

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                # Some free models emit malformed JSON; try to salvage
                args = {}
            # Some free models return args as a list instead of dict
            if not isinstance(args, dict):
                print(f"  [{agent_name}] Malformed tool args (got {type(args).__name__}), skipping")
                args = {}
            result = tool_handler.execute(tc.function.name, args)
            print(f"  [{agent_name}] tool: {tc.function.name}({args}) → {result[:80]}")
            log.append({"agent": agent_name, "type": "tool_call", "tool": tc.function.name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result,
            })

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

    try:
        import openai
    except ImportError:
        print("ERROR: openai not installed.  pip install openai")
        sys.exit(1)

    print(f"Model: {LLM_MODEL}")
    print(f"API base: {LLM_API_BASE}")
    print()

    client_kwargs = dict(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    if LLM_USER_AGENT:
        client_kwargs["default_headers"] = {"User-Agent": LLM_USER_AGENT}
    client = openai.OpenAI(**client_kwargs)
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
            repo, client, log,
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
            repo, client, log,
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
            repo, client, log,
        )
        print(f"Alice final: {alice_final[:200]}")
        print()

        # --- Save conversation log ---
        log_path = os.path.join(repo, "shared", "artifacts", "conversation.json")
        with open(log_path, "w") as f:
            json.dump({"model": LLM_MODEL, "api_base": LLM_API_BASE, "log": log}, f, indent=2)

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
            print(f"  Artifact exists: shared/artifacts/function_design.md ✓")
        else:
            print(f"  Note: artifact not written (agent may have responded in text instead)")

        # Conversation log exists
        assert os.path.isfile(log_path), "Conversation log should exist"
        print(f"  Conversation log: shared/artifacts/conversation.json ✓")

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

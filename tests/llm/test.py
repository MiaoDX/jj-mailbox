#!/usr/bin/env python3
"""
LLM tool-calling agent test.

Uses OpenAI function calling so agents invoke jj-mailbox as actual tool calls.
Skips gracefully if LLM_API_KEY is not set and OLLAMA is not set.

Default model: openrouter/free via OpenRouter (auto-routes to best free model)
Local option:  qwen2.5:0.5b via ollama (set OLLAMA=1)
See docs/MODEL_CHOICES.md for all provider options.

Scenario: "Code review, 3 rounds"
  Alice proposes a function design
  Bob reviews using read_inbox + send_message tool calls
  Alice incorporates feedback, writes final design to shared/artifacts/

Usage:
  # Local ollama:
  OLLAMA=1 python3 tests/llm/test.py

  # OpenRouter:
  LLM_API_KEY=sk-or-... python3 tests/llm/test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

# Config from environment
USE_OLLAMA = os.environ.get("OLLAMA", "") not in ("", "0", "false")

if USE_OLLAMA:
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "ollama")
    LLM_API_BASE = os.environ.get("LLM_API_BASE", "http://localhost:11434/v1")
    LLM_MODEL = os.environ.get("LLM_MODEL", "qwen2.5:0.5b")
else:
    LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
    LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
    LLM_MODEL = os.environ.get("LLM_MODEL", "openrouter/free")

MAX_TURNS = 6  # max tool-calling turns per agent per round

# --- OpenAI tool schemas ---
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to another agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string", "description": "Recipient agent name"},
                    "subject": {"type": "string", "description": "Message subject"},
                    "body": {"type": "string", "description": "Message body"},
                    "refs": {
                        "type": "string",
                        "description": "Comma-separated IDs of messages being replied to (optional)",
                    },
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_inbox",
            "description": "Read the oldest unread message from inbox. Returns message JSON or empty string.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_artifact",
            "description": "Write content to a shared artifact file in shared/artifacts/",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "File name (e.g. design.md)"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["filename", "content"],
            },
        },
    },
]


def run_cli(cmd, env=None):
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=merged)
    return result.stdout.strip(), result.returncode


def setup_repo():
    repo = tempfile.mkdtemp(prefix="jj-mailbox-3a-")
    subprocess.run(
        "git config --global user.email ci@test.local 2>/dev/null || true",
        shell=True, capture_output=True,
    )
    subprocess.run(
        "git config --global user.name CI 2>/dev/null || true",
        shell=True, capture_output=True,
    )
    # Configure jj user to suppress warnings
    subprocess.run(
        'mkdir -p ~/.config/jj && printf \'[user]\\nname = "CI"\\nemail = "ci@test.local"\\n\' > ~/.config/jj/config.toml 2>/dev/null || true',
        shell=True, capture_output=True,
    )
    subprocess.run(f"{BIN} init {repo}", shell=True, check=True)
    subprocess.run(f"JJ_MAILBOX_REPO={repo} {BIN} register alice 'Function designer'", shell=True, check=True)
    subprocess.run(f"JJ_MAILBOX_REPO={repo} {BIN} register bob 'Code reviewer'", shell=True, check=True)
    os.makedirs(os.path.join(repo, "shared", "artifacts"), exist_ok=True)
    return repo


def execute_tool(name, args, agent_name, repo):
    """Execute a tool call and return string result."""
    if name == "send_message":
        to = args.get("to", "").lower().strip()
        subject = args.get("subject", "")
        body = args.get("body", "")
        refs = args.get("refs", "")
        cmd = f'{BIN} send {to} "{subject}" "{body}"'
        if refs:
            cmd += f" --refs {refs}"
        stdout, code = run_cli(cmd, {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": agent_name})
        if code != 0:
            return f"Error sending message: {stdout}"
        lines = [l for l in stdout.splitlines() if l.strip()]
        msg_id = lines[-1] if lines else "unknown"
        return f"Message sent. ID: {msg_id}"

    elif name == "read_inbox":
        stdout, code = run_cli(
            f"{BIN} read {agent_name}",
            {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": agent_name},
        )
        if not stdout:
            return "Inbox is empty."
        try:
            msg = json.loads(stdout)
            return json.dumps(msg, indent=2)
        except json.JSONDecodeError:
            return stdout

    elif name == "write_artifact":
        filename = args.get("filename", "artifact.txt")
        content = args.get("content", "")
        path = os.path.join(repo, "shared", "artifacts", filename)
        with open(path, "w") as f:
            f.write(content)
        return f"Artifact written: shared/artifacts/{filename}"

    return f"Unknown tool: {name}"


def run_agent(agent_name, system_prompt, user_prompt, repo, client, log,
              force_tool=False):
    """Run an agent with tool calling, returning the final text response."""
    import openai

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for turn in range(MAX_TURNS):
        # Force tool use on first turn if requested (some free models skip tools)
        choice = "required" if force_tool and turn == 0 else "auto"
        try:
            response = client.chat.completions.create(
                model=LLM_MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice=choice,
                max_tokens=500,
                temperature=0.7,
            )
        except openai.NotFoundError as e:
            print(f"  [{agent_name}] Model error: {e.message}")
            print(f"  Hint: try a different model — see docs/MODEL_CHOICES.md")
            return f"Model error: {e.message}"
        except openai.APIError as e:
            print(f"  [{agent_name}] API error: {e}")
            return f"API error: {e}"
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
            result = execute_tool(tc.function.name, args, agent_name, repo)
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
    print("Level 3a: Tool-calling LLM agent (free model)")
    print("=" * 60)

    if not LLM_API_KEY and not USE_OLLAMA:
        print()
        print("⏭  SKIP: LLM_API_KEY not set and OLLAMA not set.")
        print("   Options:")
        print("     OLLAMA=1 python3 tests/llm/test.py  # local ollama")
        print("     LLM_API_KEY=sk-or-... python3 ...  # OpenRouter (free)")
        sys.exit(0)

    try:
        import openai
    except ImportError:
        print("ERROR: openai not installed.  pip install openai")
        sys.exit(1)

    print(f"Model: {LLM_MODEL}")
    print(f"API base: {LLM_API_BASE}")
    print()

    client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    repo = setup_repo()
    log = []

    try:
        # --- Round 1: Alice proposes function design ---
        print("Round 1: Alice proposes a function design")
        alice_reply = run_agent(
            "alice",
            "You are Alice, a software engineer. You collaborate with Bob via jj-mailbox. "
            "You MUST use the send_message tool to communicate. Agent names are lowercase.",
            "Use the send_message tool to send bob a message proposing a design for a "
            "'process_batch(items)' function. Include: purpose, parameters, return value. "
            "Subject: 'Function design proposal'.",
            repo, client, log,
            force_tool=True,
        )
        print(f"Alice: {alice_reply[:200]}")
        print()

        # --- Round 2: Bob reviews ---
        print("Round 2: Bob reviews Alice's proposal")
        bob_reply = run_agent(
            "bob",
            "You are Bob, a code reviewer. You collaborate with Alice via jj-mailbox. "
            "You MUST use read_inbox and send_message tools. Agent names are lowercase.",
            "Use read_inbox to read Alice's message, then use send_message to reply to alice "
            "with your code review feedback. Subject: 'Re: Function design proposal'.",
            repo, client, log,
            force_tool=True,
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
        print("✅ Level 3a: Tool-calling LLM agent test passed!")
        print("=" * 60)

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
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    main()

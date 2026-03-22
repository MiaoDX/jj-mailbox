#!/usr/bin/env python3
"""Regression tests for the reusable jj-mailbox tool adapters.

These tests stay stdlib-only and avoid live LLM calls. They verify that the
OpenAI/Codex and Claude Code adapters can be imported and that the OpenAI
execution handler still drives the CLI correctly.
"""

import json
import os
import sys


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(TESTS_DIR)
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, TESTS_DIR)

from _helpers import cleanup_repo, setup_repo
from examples.adapters.claude_code.tools import CLAUDE_TOOLS, JjMailboxClaudeTools
from examples.adapters.openai.tools import OPENAI_TOOLS, JjMailboxOpenAITools


def assert_tool_names(tools, expected_names, name_key):
    names = [tool["name"] if name_key == "name" else tool["function"]["name"] for tool in tools]
    assert names == expected_names, f"Expected tool names {expected_names}, got {names}"


def main():
    expected_names = ["send_message", "read_inbox", "write_artifact"]
    assert_tool_names(OPENAI_TOOLS, expected_names, "function")
    assert_tool_names(CLAUDE_TOOLS, expected_names, "name")

    repo = setup_repo(BIN, [("alice", "Function designer"), ("bob", "Code reviewer")], prefix="jj-mailbox-adapter-")
    try:
        alice_tools = JjMailboxOpenAITools(bin_path=BIN, repo_path=repo, agent_name="alice")
        bob_tools = JjMailboxClaudeTools(bin_path=BIN, repo_path=repo, agent_name="bob")

        send_result = alice_tools.execute(
            "send_message",
            {
                "to": "bob",
                "subject": "Adapter smoke test",
                "body": "Hello from adapter coverage.",
            },
        )
        assert "Message sent. ID:" in send_result, send_result

        read_result = bob_tools.execute("read_inbox")
        payload = json.loads(read_result)
        assert payload["from"] == "alice", payload
        assert payload["to"] == "bob", payload
        assert payload["subject"] == "Adapter smoke test", payload

        artifact_result = bob_tools.execute(
            "write_artifact",
            {
                "filename": "adapter-smoke.md",
                "content": "# Adapter smoke\n\nClaude/OpenAI adapters share execution logic.\n",
            },
        )
        assert artifact_result == "Artifact written: shared/artifacts/adapter-smoke.md", artifact_result

        artifact_path = os.path.join(repo, "shared", "artifacts", "adapter-smoke.md")
        with open(artifact_path) as f:
            content = f.read()
        assert "Claude/OpenAI adapters share execution logic." in content, content

        empty_result = bob_tools.execute("read_inbox")
        assert empty_result == "Inbox is empty.", empty_result

        unknown_result = bob_tools.execute("unknown_tool")
        assert unknown_result == "Unknown tool: unknown_tool", unknown_result

        print("✅ adapter regression tests passed")
    finally:
        cleanup_repo(repo)


if __name__ == "__main__":
    main()

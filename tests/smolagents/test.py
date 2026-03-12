#!/usr/bin/env python3
"""
Level 2b: smolagents tool-calling test.

Uses smolagents + OpenRouter free model (or any OpenAI-compatible provider).
jj-mailbox CLI is wrapped as smolagents Tool subclasses.

Skips gracefully if LLM_API_KEY is not set.

Scenario:
  Alice agent sends Bob a message about a caching design,
  then polls until Bob replies, and reads the reply.
"""
import os
import sys

# Resolve paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

# Import shared helpers
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from _helpers import setup_repo, cleanup_repo

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


def main():
    print("=" * 60)
    print("Level 2b: smolagents tool-calling test")
    print("=" * 60)

    if not LLM_API_KEY:
        print()
        print("⏭  SKIP: LLM_API_KEY not set.")
        print("   Set LLM_API_KEY to run this test with an OpenAI-compatible model.")
        sys.exit(0)

    # Import smolagents — provide a clear error if not installed
    try:
        from smolagents import CodeAgent, OpenAIServerModel
    except ImportError:
        print("ERROR: smolagents not installed.")
        print("  pip install 'smolagents[openai]'")
        sys.exit(1)

    from tools import CheckInboxTool, ReadMessageTool, SendMessageTool

    repo = setup_repo(BIN, [("alice", "API designer"), ("bob", "Code reviewer")], prefix="jj-mailbox-2b-")
    print(f"Test repo: {repo}")
    print(f"Model: {LLM_MODEL} @ {LLM_API_BASE}")
    print()

    try:
        # --- Alice agent: sends message, checks for reply ---
        alice_tools = [
            SendMessageTool("alice", repo),
            CheckInboxTool("alice", repo),
            ReadMessageTool("alice", repo),
        ]
        alice_model = OpenAIServerModel(
            model_id=LLM_MODEL, api_key=LLM_API_KEY, api_base=LLM_API_BASE
        )
        alice_agent = CodeAgent(tools=alice_tools, model=alice_model, max_steps=5)

        print("Running Alice agent...")
        alice_result = alice_agent.run(
            "You are Alice. Use the send_message tool to send Bob a message "
            "about choosing between LRU and Redis for caching. "
            "Subject: 'Caching design'. "
            "Then use check_inbox to see if Bob replied. "
            "Report what you did."
        )
        print(f"Alice result: {alice_result}")
        print()

        # --- Bob agent: reads Alice's message, replies ---
        bob_tools = [
            ReadMessageTool("bob", repo),
            SendMessageTool("bob", repo),
            CheckInboxTool("bob", repo),
        ]
        bob_model = OpenAIServerModel(
            model_id=LLM_MODEL, api_key=LLM_API_KEY, api_base=LLM_API_BASE
        )
        bob_agent = CodeAgent(tools=bob_tools, model=bob_model, max_steps=5)

        print("Running Bob agent...")
        bob_result = bob_agent.run(
            "You are Bob. Use read_message to read your latest message. "
            "Then use send_message to reply to alice with your recommendation "
            "on caching strategy. Subject: 'Re: Caching design'. "
            "Report what you did."
        )
        print(f"Bob result: {bob_result}")
        print()

        # Verify at least one message was sent by checking Bob's inbox was non-empty
        # and that files exist in processed or new dirs
        bob_new = os.path.join(repo, "inbox/bob/new")
        bob_proc = os.path.join(repo, "inbox/bob/processed")
        alice_new = os.path.join(repo, "inbox/alice/new")
        alice_proc = os.path.join(repo, "inbox/alice/processed")

        bob_msgs = (
            len([f for f in os.listdir(bob_new) if f.endswith(".json")])
            + len([f for f in os.listdir(bob_proc) if f.endswith(".json")])
        )
        alice_msgs = (
            len([f for f in os.listdir(alice_new) if f.endswith(".json")])
            + len([f for f in os.listdir(alice_proc) if f.endswith(".json")])
        )

        print(f"Messages delivered to bob: {bob_msgs}")
        print(f"Messages delivered to alice: {alice_msgs}")

        assert bob_msgs >= 1, "Bob should have received at least 1 message from Alice"
        print()
        print("=" * 60)
        print("✅ Level 2b: smolagents test passed!")
        print("=" * 60)

    finally:
        cleanup_repo(repo)


if __name__ == "__main__":
    main()

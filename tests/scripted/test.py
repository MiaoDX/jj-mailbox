#!/usr/bin/env python3
"""
Level 2a: Scripted agent test — deterministic multi-turn conversation.

Pure stdlib, no pip installs, no API keys required.

Scenario: "Research task, 3 turns"
  Planner → Researcher: "List 3 caching strategies."
  Researcher → Planner (refs=original): "LRU, Redis, File cache."
  Planner → Researcher (refs=reply): "Got it. Proceeding with LRU."
  Planner writes summary to shared/artifacts/plan.txt

Assertions:
  - refs chain intact (msg2 refs msg1, msg3 refs msg2)
  - processed/ has all messages
  - shared artifact exists
  - message ordering correct
"""
import json
import os
import sys

# Find jj-mailbox binary relative to this file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

# Import shared helpers
sys.path.insert(0, os.path.join(SCRIPT_DIR, ".."))
from _helpers import (
    cleanup_repo,
    count_messages,
    read_message,
    run_cli,
    send_message,
    setup_repo,
)


def assert_eq(a, b, msg=""):
    if a != b:
        print(f"ASSERT FAIL: {msg}")
        print(f"  expected: {b!r}")
        print(f"     got: {a!r}")
        sys.exit(1)


def assert_in(needle, haystack, msg=""):
    if needle not in haystack:
        print(f"ASSERT FAIL: {msg}")
        print(f"  {needle!r} not in {haystack!r}")
        sys.exit(1)


def main():
    print("=" * 60)
    print("Level 2a: Scripted agent test")
    print("=" * 60)
    print()

    repo = setup_repo(BIN, [("planner", "Task planner"), ("researcher", "Research specialist")])
    print(f"Test repo: {repo}")
    print()

    try:
        # --- Turn 1: Planner → Researcher ---
        print("Turn 1: planner → researcher: 'List 3 caching strategies.'")
        msg1_id = send_message(BIN, repo, "planner", "researcher", "Research task", "List 3 caching strategies.")
        assert msg1_id, "msg1_id should not be empty"
        print(f"  msg1 id: {msg1_id}")

        # Researcher has 1 new message
        assert_eq(count_messages(repo, "researcher", "new"), 1, "researcher should have 1 new message")

        # --- Turn 2: Researcher reads and replies with refs=[msg1_id] ---
        print("Turn 2: researcher reads, replies with refs=[msg1_id]")
        msg1 = read_message(BIN, repo, "researcher")
        assert msg1 is not None, "researcher should be able to read msg1"
        assert_eq(msg1["from"], "planner", "msg1 from should be 'planner'")
        assert_eq(msg1["id"], msg1_id, "msg1 id should match")

        msg2_id = send_message(BIN, repo, "researcher", "planner", "Re: Research task", "LRU, Redis, File cache.", refs=[msg1_id])
        assert msg2_id, "msg2_id should not be empty"
        print(f"  msg2 id: {msg2_id}")

        # Verify msg2 refs contains msg1_id
        msg2_file = sorted([
            f for f in os.listdir(os.path.join(repo, "inbox/planner/new")) if f.endswith(".json")
        ])[-1]
        with open(os.path.join(repo, "inbox/planner/new", msg2_file)) as f:
            msg2_data = json.load(f)
        assert_in(msg1_id, msg2_data["refs"], "msg2 refs should contain msg1_id")
        print(f"  msg2 refs: {msg2_data['refs']} ✓")

        # --- Turn 3: Planner reads reply, sends ack with refs=[msg2_id] ---
        print("Turn 3: planner reads, acks with refs=[msg2_id]")
        msg2 = read_message(BIN, repo, "planner")
        assert msg2 is not None, "planner should be able to read msg2"
        assert_eq(msg2["from"], "researcher", "msg2 from should be 'researcher'")

        msg3_id = send_message(BIN, repo, "planner", "researcher", "Re: Research task", "Got it. Proceeding with LRU.", refs=[msg2_id])
        assert msg3_id, "msg3_id should not be empty"
        print(f"  msg3 id: {msg3_id}")

        # Verify msg3 refs contains msg2_id
        msg3_file = sorted([
            f for f in os.listdir(os.path.join(repo, "inbox/researcher/new")) if f.endswith(".json")
        ])[-1]
        with open(os.path.join(repo, "inbox/researcher/new", msg3_file)) as f:
            msg3_data = json.load(f)
        assert_in(msg2_id, msg3_data["refs"], "msg3 refs should contain msg2_id")
        print(f"  msg3 refs: {msg3_data['refs']} ✓")

        # Read msg3 to move to processed
        read_message(BIN, repo, "researcher")

        # --- Write shared artifact ---
        print("Writing shared artifact: shared/artifacts/plan.txt")
        artifact_path = os.path.join(repo, "shared", "artifacts", "plan.txt")
        with open(artifact_path, "w") as f:
            f.write("# Caching Plan\n\nSelected strategy: LRU\n\nBased on research:\n- LRU: Least Recently Used, simple and effective\n- Redis: distributed, needs server\n- File cache: slow, disk-bound\n\nDecision: LRU for in-process caching.\n")
        print(f"  Artifact written: {artifact_path}")

        # --- Final assertions ---
        print()
        print("Assertions:")

        # All messages processed
        planner_proc = count_messages(repo, "planner", "processed")
        researcher_proc = count_messages(repo, "researcher", "processed")
        print(f"  planner processed: {planner_proc}")
        print(f"  researcher processed: {researcher_proc}")
        assert planner_proc >= 1, f"planner should have >= 1 processed msg, got {planner_proc}"
        assert researcher_proc >= 2, f"researcher should have >= 2 processed msgs, got {researcher_proc}"

        # Inbox empty
        assert_eq(count_messages(repo, "planner", "new"), 0, "planner inbox should be empty")
        assert_eq(count_messages(repo, "researcher", "new"), 0, "researcher inbox should be empty")

        # Artifact exists
        assert os.path.isfile(artifact_path), "shared artifact should exist"
        print(f"  shared artifact exists ✓")

        # Refs chain verified above ✓

        # Thread view reconstructs the full conversation from the middle message
        thread_out, _, _ = run_cli(
            [BIN, "thread", msg2_id],
            env={"JJ_MAILBOX_REPO": repo},
        )
        print("Thread view:")
        print(thread_out)
        assert_in('Turn 1  planner → researcher  "Research task"', thread_out, "thread should include turn 1")
        assert_in(f'Turn 2  researcher → planner  "Re: Research task"  [refs: {msg1_id}]', thread_out, "thread should include turn 2")
        assert_in(f'Turn 3  planner → researcher  "Re: Research task"  [refs: {msg2_id}]', thread_out, "thread should include turn 3")

        print()
        print("=" * 60)
        print("✅ Level 2a: All assertions passed!")
        print("=" * 60)

    finally:
        cleanup_repo(repo)


if __name__ == "__main__":
    main()

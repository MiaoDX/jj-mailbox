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
import subprocess
import sys
import tempfile
import time
import shutil

REPO_PATH = os.environ.get("JJ_MAILBOX_REPO", "")
# Find jj-mailbox binary relative to this file
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")


def run(cmd, env=None, check=True):
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, env=merged_env
    )
    if check and result.returncode != 0:
        print(f"FAIL: {cmd}")
        print(f"  stdout: {result.stdout.strip()}")
        print(f"  stderr: {result.stderr.strip()}")
        sys.exit(1)
    return result.stdout.strip()


def send(frm, to, subject, body, refs=None, repo=None):
    """Send a message and return its ID."""
    repo = repo or REPO_PATH
    cmd = f'JJ_MAILBOX_REPO={repo} JJ_MAILBOX_AGENT={frm} {BIN} send {to} "{subject}" "{body}"'
    if refs:
        cmd += f" --refs {','.join(refs)}"
    output = run(cmd)
    # The last line of output is the message ID
    lines = [l for l in output.splitlines() if l.strip()]
    msg_id = lines[-1] if lines else ""
    return msg_id


def read_msg(agent, repo=None):
    """Read oldest message from agent's inbox, return parsed JSON."""
    repo = repo or REPO_PATH
    cmd = f'JJ_MAILBOX_REPO={repo} JJ_MAILBOX_AGENT={agent} {BIN} read {agent}'
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=os.environ)
    if result.returncode != 0:
        return None
    # Parse JSON from stdout (the first { ... } block)
    stdout = result.stdout.strip()
    # Find JSON object in output
    for line in stdout.splitlines():
        if line.strip().startswith("{"):
            break
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Try to extract just the JSON part
        import re
        m = re.search(r'\{.*\}', stdout, re.DOTALL)
        if m:
            return json.loads(m.group(0))
        return None


def count_processed(agent, repo=None):
    repo = repo or REPO_PATH
    d = os.path.join(repo, f"inbox/{agent}/processed")
    return len([f for f in os.listdir(d) if f.endswith(".json")]) if os.path.isdir(d) else 0


def count_new(agent, repo=None):
    repo = repo or REPO_PATH
    d = os.path.join(repo, f"inbox/{agent}/new")
    return len([f for f in os.listdir(d) if f.endswith(".json")]) if os.path.isdir(d) else 0


def setup_repo():
    """Initialize a fresh test repo."""
    repo = tempfile.mkdtemp(prefix="jj-mailbox-test-")
    run(f"git config --global user.email ci@test.local 2>/dev/null || true", check=False)
    run(f"git config --global user.name CI 2>/dev/null || true", check=False)
    run(f"{BIN} init {repo}")
    run(f"JJ_MAILBOX_REPO={repo} {BIN} register planner 'Task planner'")
    run(f"JJ_MAILBOX_REPO={repo} {BIN} register researcher 'Research specialist'")
    os.makedirs(os.path.join(repo, "shared", "artifacts"), exist_ok=True)
    return repo


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

    repo = setup_repo()
    print(f"Test repo: {repo}")
    print()

    try:
        # --- Turn 1: Planner → Researcher ---
        print("Turn 1: planner → researcher: 'List 3 caching strategies.'")
        msg1_id = send("planner", "researcher", "Research task", "List 3 caching strategies.", repo=repo)
        assert msg1_id, "msg1_id should not be empty"
        print(f"  msg1 id: {msg1_id}")

        # Researcher has 1 new message
        assert_eq(count_new("researcher", repo), 1, "researcher should have 1 new message")

        # --- Turn 2: Researcher reads and replies with refs=[msg1_id] ---
        print("Turn 2: researcher reads, replies with refs=[msg1_id]")
        msg1 = read_msg("researcher", repo)
        assert msg1 is not None, "researcher should be able to read msg1"
        assert_eq(msg1["from"], "planner", "msg1 from should be 'planner'")
        assert_eq(msg1["id"], msg1_id, "msg1 id should match")

        msg2_id = send("researcher", "planner", "Re: Research task", "LRU, Redis, File cache.", refs=[msg1_id], repo=repo)
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
        msg2 = read_msg("planner", repo)
        assert msg2 is not None, "planner should be able to read msg2"
        assert_eq(msg2["from"], "researcher", "msg2 from should be 'researcher'")

        msg3_id = send("planner", "researcher", "Re: Research task", "Got it. Proceeding with LRU.", refs=[msg2_id], repo=repo)
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
        read_msg("researcher", repo)

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
        planner_proc = count_processed("planner", repo)
        researcher_proc = count_processed("researcher", repo)
        print(f"  planner processed: {planner_proc}")
        print(f"  researcher processed: {researcher_proc}")
        assert planner_proc >= 1, f"planner should have >= 1 processed msg, got {planner_proc}"
        assert researcher_proc >= 2, f"researcher should have >= 2 processed msgs, got {researcher_proc}"

        # Inbox empty
        assert_eq(count_new("planner", repo), 0, "planner inbox should be empty")
        assert_eq(count_new("researcher", repo), 0, "researcher inbox should be empty")

        # Artifact exists
        assert os.path.isfile(artifact_path), "shared artifact should exist"
        print(f"  shared artifact exists ✓")

        # Refs chain verified above ✓

        print()
        print("=" * 60)
        print("✅ Level 2a: All assertions passed!")
        print("=" * 60)

    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    main()

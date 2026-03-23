#!/usr/bin/env python3
"""Regression test for `jj-mailbox watch` polling mode without requiring `jj`."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(REPO_ROOT)
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")


def wait_for_file(path: str, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            return True
        time.sleep(0.2)
    return False


def make_repo() -> str:
    repo = tempfile.mkdtemp(prefix="jj-mailbox-watch-")
    os.makedirs(os.path.join(repo, ".jj"), exist_ok=True)
    os.makedirs(os.path.join(repo, "inbox", "bob", "new"), exist_ok=True)
    os.makedirs(os.path.join(repo, "inbox", "bob", "processed"), exist_ok=True)
    return repo


def write_message(repo: str) -> None:
    path = os.path.join(repo, "inbox", "bob", "new", "2026-03-23T00-00-00Z_alice_msg-test.json")
    with open(path, "w") as f:
        json.dump({"id": "msg-test", "from": "alice", "to": "bob", "subject": "Ping", "body": "watch test"}, f)


def main() -> int:
    repo = make_repo()
    hook_dir = tempfile.mkdtemp(prefix="jj-mailbox-hook-")
    hook_file = os.path.join(hook_dir, "triggered.txt")

    watch_env = {
        **os.environ,
        "JJ_MAILBOX_REPO": repo,
        "JJ_MAILBOX_AGENT": "bob",
        "JJ_MAILBOX_FORCE_POLL": "1",
        "WATCH_OUTPUT": hook_file,
    }
    watch_cmd = [BIN, "watch", "--exec", 'printf "triggered\\n" >> "$WATCH_OUTPUT"']
    watcher = subprocess.Popen(
        watch_cmd,
        env=watch_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        time.sleep(1.0)
        write_message(repo)
        if not wait_for_file(hook_file):
            stdout, stderr = watcher.communicate(timeout=1)
            print("watch hook was not triggered")
            print("stdout:\n", stdout)
            print("stderr:\n", stderr)
            return 1

        with open(hook_file) as f:
            contents = f.read()
        if "triggered" not in contents:
            print("watch hook file did not contain expected marker")
            print(contents)
            return 1
        return 0
    finally:
        watcher.terminate()
        try:
            watcher.wait(timeout=2)
        except subprocess.TimeoutExpired:
            watcher.kill()
            watcher.wait(timeout=2)
        shutil.rmtree(repo, ignore_errors=True)
        shutil.rmtree(hook_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())

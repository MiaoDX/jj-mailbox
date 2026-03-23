#!/usr/bin/env python3
"""Regression tests for task workflow and hook handling."""

import json
import os

from _helpers import cleanup_repo, read_message, run_cli, setup_repo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")


def write_hook(repo: str, body: str) -> None:
    with open(os.path.join(repo, "config", "hooks.yaml"), "w") as f:
        f.write(body)


def load_task(repo: str, task_id: str) -> dict:
    with open(os.path.join(repo, "shared", "tasks", f"{task_id}.json")) as f:
        return json.load(f)


def main():
    repo = setup_repo(BIN, [("lead", "Lead"), ("alice", "Implementer"), ("bob", "Reviewer")], prefix="jj-mailbox-task-")
    try:
        task1_out, _, _ = run_cli(
            [BIN, "task", "create", "Build API", "--priority", "2"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "lead"},
        )
        task1 = task1_out.splitlines()[-1]

        task2_out, _, _ = run_cli(
            [BIN, "task", "create", "Ship API", "--priority", "1", "--blocked-by", task1],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "lead"},
        )
        task2 = task2_out.splitlines()[-1]

        claim_out, _, _ = run_cli(
            [BIN, "task", "claim"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "alice"},
        )
        assert claim_out.splitlines()[-1] == task1, claim_out

        list_out, _, _ = run_cli([BIN, "task", "list"], env={"JJ_MAILBOX_REPO": repo})
        assert f"{task1}\tin_progress\tP2\talice" in list_out, list_out
        assert f"{task2}\tpending\tP1\t-\tblockedBy={task1}" in list_out, list_out

        write_hook(
            repo,
            """on_task_complete:
  - name: reject-unfinished
    command: "echo need more work >&2; exit 2"
""",
        )
        _, reject_stderr, reject_code = run_cli(
            [BIN, "task", "complete", task1],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "alice"},
            check=False,
        )
        assert reject_code == 2, reject_code
        assert "need more work" in reject_stderr, reject_stderr
        assert load_task(repo, task1)["status"] == "in_progress"

        feedback = read_message(BIN, repo, "alice")
        assert feedback is not None, "Expected hook rejection feedback message"
        assert feedback["type"] == "reply", feedback
        assert task1 in feedback["subject"], feedback

        write_hook(repo, "on_task_complete: []\n")
        run_cli(
            [BIN, "task", "complete", task1],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "alice"},
        )

        task1_payload = load_task(repo, task1)
        assert task1_payload["status"] == "completed", task1_payload
        assert task1_payload["assignee"] == "alice", task1_payload

        claim2_out, _, _ = run_cli(
            [BIN, "task", "claim"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "bob"},
        )
        assert claim2_out.splitlines()[-1] == task2, claim2_out

        send_out, _, _ = run_cli(
            [BIN, "send", "lead", "Awaiting review", "Please confirm.", "--type", "approval_request"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "bob"},
        )
        assert "msg-" in send_out, send_out

        status_out, _, _ = run_cli([BIN, "status"], env={"JJ_MAILBOX_REPO": repo})
        assert "💤 alice  (idle)" in status_out, status_out
        assert "🟡 bob  (busy)" in status_out, status_out

        print("✅ task workflow regression tests passed")
    finally:
        cleanup_repo(repo)


if __name__ == "__main__":
    main()

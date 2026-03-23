#!/usr/bin/env python3
"""Regression tests for explicit mailbox message types."""

import json
import os
import stat
import tempfile
from pathlib import Path

from _helpers import cleanup_repo, run_cli, setup_repo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")


def make_fake_jj() -> str:
    tmpdir = tempfile.mkdtemp(prefix="jj-mailbox-fake-jj-")
    script = Path(tmpdir) / "jj"
    script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
case "$1 ${2-} ${3-}" in
  'git init --colocate') mkdir -p .jj .git ;;
  'git clone --colocate') mkdir -p .jj .git ;;
  'git fetch --all-remotes') exit 0 ;;
  'git push --all') exit 0 ;;
  'status  ') exit 0 ;;
  'commit -m') exit 0 ;;
  *) exit 0 ;;
esac
"""
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return tmpdir


def main():
    fake_jj = make_fake_jj()
    original_path = os.environ["PATH"]
    path_env = f"{fake_jj}:{original_path}"
    os.environ["PATH"] = path_env
    repo = setup_repo(BIN, [("alice", "Agent"), ("bob", "Agent")], prefix="jj-mailbox-message-types-")
    try:
        run_cli(
            [BIN, "send", "bob", "Need approval", "Please confirm rollout.", "--type", "approval_request"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "alice", "PATH": path_env},
        )

        inbox_dir = Path(repo) / "inbox" / "bob" / "new"
        message_file = next(path for path in inbox_dir.iterdir() if path.suffix == ".json")
        payload = json.loads(message_file.read_text())
        assert payload["type"] == "approval_request", payload

        status_file = Path(repo) / "agents" / "bob" / "status.json"
        status = json.loads(status_file.read_text())
        status["status"] = "waiting_approval"
        status_file.write_text(json.dumps(status))

        status_out, _, _ = run_cli([BIN, "status"], env={"JJ_MAILBOX_REPO": repo, "PATH": path_env})
        assert "🟣 bob  (waiting_approval)" in status_out, status_out

        _, stderr, code = run_cli(
            [BIN, "send", "bob", "Bad", "Nope", "--type", "not_real"],
            env={"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": "alice", "PATH": path_env},
            check=False,
        )
        assert code != 0, code
        assert "Unsupported message type" in stderr, stderr

        print("✅ message type regression tests passed")
    finally:
        os.environ["PATH"] = original_path
        cleanup_repo(repo)
        cleanup_repo(fake_jj)


if __name__ == "__main__":
    main()

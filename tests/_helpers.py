"""
Shared test utilities for jj-mailbox tests.

Stdlib-only — no pip dependencies required.
All subprocess calls use list-form arguments (no shell=True) to prevent injection.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile


def run_cli(cmd_args, env=None, check=True):
    """Run a CLI command safely using list-form subprocess (no shell=True).

    Args:
        cmd_args: List of command arguments, e.g. [BIN, "send", "bob", "Hi", "Hello"]
        env: Extra environment variables to merge with os.environ
        check: If True, raise on non-zero exit code

    Returns:
        (stdout, stderr, returncode) tuple
    """
    merged_env = {**os.environ, **(env or {})}
    result = subprocess.run(
        cmd_args,
        capture_output=True,
        text=True,
        env=merged_env,
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, cmd_args,
            result.stdout, result.stderr,
        )
    return result.stdout.strip(), result.stderr.strip(), result.returncode


def setup_repo(bin_path, agents, prefix="jj-mailbox-test-"):
    """Initialize a fresh test repo with registered agents.

    Args:
        bin_path: Path to the jj-mailbox binary
        agents: List of (name, description) tuples
        prefix: Temp directory prefix

    Returns:
        Path to the created repo directory
    """
    repo = tempfile.mkdtemp(prefix=prefix)
    # Configure git/jj user (ignore errors if already set)
    subprocess.run(
        ["git", "config", "--global", "user.email", "ci@test.local"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "--global", "user.name", "CI"],
        capture_output=True,
    )
    # Configure jj user to suppress warnings
    jj_config_dir = os.path.expanduser("~/.config/jj")
    os.makedirs(jj_config_dir, exist_ok=True)
    config_path = os.path.join(jj_config_dir, "config.toml")
    if not os.path.exists(config_path):
        with open(config_path, "w") as f:
            f.write('[user]\nname = "CI"\nemail = "ci@test.local"\n')

    # Init repo
    run_cli([bin_path, "init", repo])

    # Register agents
    for name, desc in agents:
        run_cli(
            [bin_path, "register", name, desc],
            env={"JJ_MAILBOX_REPO": repo},
        )

    # Ensure shared directories exist
    os.makedirs(os.path.join(repo, "shared", "artifacts"), exist_ok=True)
    return repo


def send_message(bin_path, repo, from_agent, to_agent, subject, body, refs=None):
    """Send a message safely and return the message ID.

    Args:
        bin_path: Path to the jj-mailbox binary
        repo: Path to the mailbox repo
        from_agent: Sender agent name
        to_agent: Recipient agent name
        subject: Message subject
        body: Message body
        refs: Optional list of message IDs being replied to

    Returns:
        The message ID string
    """
    cmd = [bin_path, "send", to_agent, subject, body]
    if refs:
        cmd += ["--refs", ",".join(refs)]
    env = {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": from_agent}
    stdout, _, _ = run_cli(cmd, env=env)
    lines = [line for line in stdout.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def read_message(bin_path, repo, agent):
    """Read the oldest unread message from an agent's inbox.

    Returns:
        Parsed JSON dict, or None if inbox is empty or parse fails
    """
    cmd = [bin_path, "read", agent]
    env = {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": agent}
    stdout, _, returncode = run_cli(cmd, env=env, check=False)
    if returncode != 0 or not stdout:
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        # Try to extract JSON object from mixed output
        m = re.search(r'\{.*\}', stdout, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        return None


def count_messages(repo, agent, folder="new"):
    """Count JSON message files in an agent's inbox folder.

    Args:
        repo: Path to the mailbox repo
        agent: Agent name
        folder: "new" or "processed"

    Returns:
        Number of .json files in the folder
    """
    d = os.path.join(repo, "inbox", agent, folder)
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".json")])


def cleanup_repo(repo_path):
    """Remove a test repo directory."""
    shutil.rmtree(repo_path, ignore_errors=True)

"""
jj-mailbox CLI wrapped as smolagents Tool subclasses.

Each tool calls the bin/jj-mailbox CLI and returns structured output.
All subprocess calls use list-form arguments (no shell=True) to prevent injection.
"""
import json
import os
import sys

from smolagents import Tool

# Resolve bin path relative to this file
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(os.path.dirname(_TOOLS_DIR))
DEFAULT_BIN = os.path.join(_REPO_ROOT, "bin", "jj-mailbox")

# Import shared helpers
sys.path.insert(0, os.path.join(_TOOLS_DIR, ".."))
from _helpers import run_cli


class SendMessageTool(Tool):
    name = "send_message"
    description = (
        "Send a message to another agent via jj-mailbox. "
        "Returns the message ID on success."
    )
    inputs = {
        "to": {"type": "string", "description": "Recipient agent name"},
        "subject": {"type": "string", "description": "Message subject"},
        "body": {"type": "string", "description": "Message body"},
        "refs": {
            "type": "string",
            "description": "Comma-separated IDs of messages this replies to (optional)",
            "nullable": True,
        },
    }
    output_type = "string"

    def __init__(self, agent_name: str, repo_path: str, bin_path: str = DEFAULT_BIN):
        super().__init__()
        self.agent_name = agent_name
        self.repo_path = repo_path
        self.bin_path = bin_path

    def forward(self, to: str, subject: str, body: str, refs: str = "") -> str:
        to = to.lower()  # jj-mailbox agent names are lowercase
        cmd = [self.bin_path, "send", to, subject, body]
        if refs:
            cmd += ["--refs", refs]
        env = {"JJ_MAILBOX_REPO": self.repo_path, "JJ_MAILBOX_AGENT": self.agent_name}
        stdout, stderr, code = run_cli(cmd, env=env, check=False)
        if code != 0:
            return f"ERROR: {stderr}"
        lines = [l for l in stdout.splitlines() if l.strip()]
        msg_id = lines[-1] if lines else "unknown"
        return f"Message sent. ID: {msg_id}"


class ReadMessageTool(Tool):
    name = "read_message"
    description = (
        "Read the oldest unread message from this agent's inbox. "
        "Returns the message as JSON, or empty string if inbox is empty."
    )
    inputs = {}
    output_type = "string"

    def __init__(self, agent_name: str, repo_path: str, bin_path: str = DEFAULT_BIN):
        super().__init__()
        self.agent_name = agent_name
        self.repo_path = repo_path
        self.bin_path = bin_path

    def forward(self) -> str:
        env = {"JJ_MAILBOX_REPO": self.repo_path, "JJ_MAILBOX_AGENT": self.agent_name}
        stdout, stderr, code = run_cli(
            [self.bin_path, "read", self.agent_name], env=env, check=False
        )
        if not stdout:
            return "Inbox is empty."
        # Try to parse and pretty-print JSON
        try:
            msg = json.loads(stdout)
            return json.dumps(msg, indent=2)
        except json.JSONDecodeError:
            return stdout


class CheckInboxTool(Tool):
    name = "check_inbox"
    description = "Check how many unread messages are in this agent's inbox."
    inputs = {}
    output_type = "string"

    def __init__(self, agent_name: str, repo_path: str, bin_path: str = DEFAULT_BIN):
        super().__init__()
        self.agent_name = agent_name
        self.repo_path = repo_path
        self.bin_path = bin_path

    def forward(self) -> str:
        env = {"JJ_MAILBOX_REPO": self.repo_path, "JJ_MAILBOX_AGENT": self.agent_name}
        stdout, stderr, code = run_cli(
            [self.bin_path, "inbox", self.agent_name], env=env, check=False
        )
        return stdout or "Inbox empty."


class GetStatusTool(Tool):
    name = "get_status"
    description = "Get the status of all registered agents in the mailbox."
    inputs = {}
    output_type = "string"

    def __init__(self, repo_path: str, bin_path: str = DEFAULT_BIN):
        super().__init__()
        self.repo_path = repo_path
        self.bin_path = bin_path

    def forward(self) -> str:
        env = {"JJ_MAILBOX_REPO": self.repo_path}
        stdout, stderr, code = run_cli(
            [self.bin_path, "status"], env=env, check=False
        )
        return stdout or "No agents registered."

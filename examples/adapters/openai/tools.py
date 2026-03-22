"""OpenAI/Codex function-calling adapter for jj-mailbox.

This module exposes reusable OpenAI-compatible tool schemas and a handler that
executes each tool against the local ``jj-mailbox`` CLI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import subprocess


OPENAI_TOOLS = [
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


class JjMailboxOpenAITools:
    """Handler for OpenAI/Codex function calls."""

    def __init__(self, bin_path: str, repo_path: str, agent_name: str):
        self.bin_path = bin_path
        self.repo_path = repo_path
        self.agent_name = agent_name

    def execute(self, tool_name: str, args: dict[str, Any] | None = None) -> str:
        args = args or {}
        if tool_name == "send_message":
            to = str(args.get("to", "")).lower().strip()
            subject = str(args.get("subject", ""))
            body = str(args.get("body", ""))
            refs = str(args.get("refs", ""))
            cmd = [self.bin_path, "send", to, subject, body]
            if refs:
                cmd += ["--refs", refs]
            stdout, stderr, code = self._run_cli(cmd)
            if code != 0:
                return f"Error sending message: {stderr}"
            lines = [line for line in stdout.splitlines() if line.strip()]
            msg_id = lines[-1] if lines else "unknown"
            return f"Message sent. ID: {msg_id}"

        if tool_name == "read_inbox":
            stdout, _stderr, code = self._run_cli([self.bin_path, "read", self.agent_name])
            if code != 0 or not stdout:
                return "Inbox is empty."
            try:
                return json.dumps(json.loads(stdout), indent=2)
            except json.JSONDecodeError:
                return stdout

        if tool_name == "write_artifact":
            filename = str(args.get("filename", "artifact.txt"))
            content = str(args.get("content", ""))
            target = Path(self.repo_path) / "shared" / "artifacts" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return f"Artifact written: shared/artifacts/{filename}"

        return f"Unknown tool: {tool_name}"

    def _run_cli(self, cmd_args: list[str]) -> tuple[str, str, int]:
        env = {
            **os.environ,
            "JJ_MAILBOX_REPO": self.repo_path,
            "JJ_MAILBOX_AGENT": self.agent_name,
        }
        result = subprocess.run(cmd_args, capture_output=True, text=True, env=env)
        return result.stdout.strip(), result.stderr.strip(), result.returncode

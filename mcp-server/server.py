#!/usr/bin/env python3
"""FastMCP wrapper for jj-mailbox.

Expose jj-mailbox operations as MCP tools so any MCP-compatible agent can use the
mailbox without shell-specific wrappers.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover - exercised in environments without MCP installed
    FastMCP = None


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BIN = ROOT / "bin" / "jj-mailbox"
DEFAULT_REPO = Path(os.environ.get("JJ_MAILBOX_REPO", os.getcwd())).resolve()
DEFAULT_AGENT = os.environ.get("JJ_MAILBOX_AGENT", os.environ.get("USER", "agent"))
DEFAULT_TRANSPORT = os.environ.get("JJ_MAILBOX_MCP_TRANSPORT", "stdio")


@dataclass(frozen=True)
class ServerSettings:
    """Runtime configuration for the jj-mailbox MCP server."""

    bin_path: Path
    repo_path: Path
    agent_name: str


class JjMailboxMCPTools:
    """Dispatch jj-mailbox CLI commands for MCP tool handlers."""

    def __init__(self, settings: ServerSettings):
        self.settings = settings

    def send_message(self, to: str, subject: str, body: str, refs: str = "") -> str:
        recipient = to.lower().strip()
        cmd = [str(self.settings.bin_path), "send", recipient, subject, body]
        if refs.strip():
            cmd += ["--refs", refs]
        stdout, stderr, code = self._run_cli(cmd)
        if code != 0:
            return self._format_error("send_message", stderr)
        lines = [line for line in stdout.splitlines() if line.strip()]
        msg_id = lines[-1] if lines else "unknown"
        return f"Message sent. ID: {msg_id}"

    def read_inbox(self) -> str:
        stdout, stderr, code = self._run_cli(
            [str(self.settings.bin_path), "read", self.settings.agent_name]
        )
        if code != 0 or not stdout:
            return "Inbox is empty."
        try:
            return json.dumps(json.loads(stdout), indent=2)
        except json.JSONDecodeError:
            if stderr:
                return self._format_error("read_inbox", stderr)
            return stdout

    def check_inbox(self) -> str:
        stdout, stderr, code = self._run_cli(
            [str(self.settings.bin_path), "inbox", self.settings.agent_name]
        )
        if code != 0:
            return self._format_error("check_inbox", stderr)
        return stdout or "Inbox empty."

    def get_status(self) -> str:
        stdout, stderr, code = self._run_cli([str(self.settings.bin_path), "status"])
        if code != 0:
            return self._format_error("get_status", stderr)
        return stdout or "No agents registered."

    def write_artifact(self, filename: str, content: str) -> str:
        if not filename.strip():
            return "Error in write_artifact: filename is required"
        target = self._artifact_path(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"Artifact written: shared/artifacts/{target.relative_to(self.settings.repo_path / 'shared' / 'artifacts')}"

    def _artifact_path(self, filename: str) -> Path:
        artifact_root = (self.settings.repo_path / "shared" / "artifacts").resolve()
        candidate = (artifact_root / filename).resolve()
        try:
            candidate.relative_to(artifact_root)
        except ValueError:
            raise ValueError("filename must stay inside shared/artifacts") from None
        return candidate

    def _run_cli(self, cmd_args: list[str]) -> tuple[str, str, int]:
        env = {
            **os.environ,
            "JJ_MAILBOX_REPO": str(self.settings.repo_path),
            "JJ_MAILBOX_AGENT": self.settings.agent_name,
        }
        result = subprocess.run(cmd_args, capture_output=True, text=True, env=env)
        return result.stdout.strip(), result.stderr.strip(), result.returncode

    @staticmethod
    def _format_error(tool_name: str, stderr: str) -> str:
        message = stderr or "unknown error"
        return f"Error in {tool_name}: {message}"


def build_server(settings: ServerSettings):
    """Create a FastMCP server instance with jj-mailbox tools registered."""
    if FastMCP is None:
        raise RuntimeError(
            "The MCP Python SDK is not installed. Install dependencies from "
            "mcp-server/requirements.txt first."
        )

    tools = JjMailboxMCPTools(settings)
    mcp = FastMCP(
        "jj-mailbox",
        instructions=(
            "Use these tools to send and receive messages through a jj-mailbox "
            "repository for the configured agent."
        ),
    )

    @mcp.tool()
    def send_message(to: str, subject: str, body: str, refs: str = "") -> str:
        """Send a message to another registered agent."""
        return tools.send_message(to=to, subject=subject, body=body, refs=refs)

    @mcp.tool()
    def read_inbox() -> str:
        """Read and mark the oldest unread message for the configured agent."""
        return tools.read_inbox()

    @mcp.tool()
    def check_inbox() -> str:
        """List unread messages for the configured agent."""
        return tools.check_inbox()

    @mcp.tool()
    def get_status() -> str:
        """Show mailbox status for all registered agents."""
        return tools.get_status()

    @mcp.tool()
    def write_artifact(filename: str, content: str) -> str:
        """Write shared output to shared/artifacts/."""
        try:
            return tools.write_artifact(filename=filename, content=content)
        except ValueError as exc:
            return f"Error in write_artifact: {exc}"

    return mcp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run jj-mailbox as a FastMCP server")
    parser.add_argument("--bin", default=str(DEFAULT_BIN), help="Path to the jj-mailbox CLI binary")
    parser.add_argument("--repo", default=str(DEFAULT_REPO), help="Path to the mailbox repository")
    parser.add_argument("--agent", default=DEFAULT_AGENT, help="Agent name to operate as")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default=DEFAULT_TRANSPORT,
        help="MCP transport to use (default: stdio)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = ServerSettings(
        bin_path=Path(args.bin).resolve(),
        repo_path=Path(args.repo).resolve(),
        agent_name=args.agent,
    )
    server = build_server(settings)
    server.run(transport=args.transport)


if __name__ == "__main__":
    main()

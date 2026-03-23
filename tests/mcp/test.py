#!/usr/bin/env python3
"""Regression tests for the jj-mailbox FastMCP wrapper.

These tests remain stdlib-only by injecting a tiny fake FastMCP implementation,
so they can validate tool registration and command dispatch without installing
third-party dependencies or the jj CLI.
"""

import importlib.util
import json
import os
import sys
import tempfile
import types

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.dirname(SCRIPT_DIR)
REPO_ROOT = os.path.dirname(TESTS_DIR)
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")
SERVER_PATH = os.path.join(REPO_ROOT, "mcp-server", "server.py")


class FakeFastMCP:
    def __init__(self, name, instructions=None):
        self.name = name
        self.instructions = instructions
        self.tools = {}

    def tool(self):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn
        return decorator

    def run(self, transport="stdio"):
        self.transport = transport


def load_server_module():
    fake_mcp = types.ModuleType("mcp")
    fake_server_pkg = types.ModuleType("mcp.server")
    fake_fastmcp = types.ModuleType("mcp.server.fastmcp")
    fake_fastmcp.FastMCP = FakeFastMCP

    sys.modules["mcp"] = fake_mcp
    sys.modules["mcp.server"] = fake_server_pkg
    sys.modules["mcp.server.fastmcp"] = fake_fastmcp

    spec = importlib.util.spec_from_file_location("jj_mailbox_mcp_server", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    module = load_server_module()
    expected_names = ["send_message", "read_inbox", "check_inbox", "get_status", "write_artifact"]

    with tempfile.TemporaryDirectory(prefix="jj-mailbox-mcp-") as repo:
        os.makedirs(os.path.join(repo, "shared", "artifacts"), exist_ok=True)
        settings = module.ServerSettings(
            bin_path=module.Path(BIN),
            repo_path=module.Path(repo),
            agent_name="alice",
        )
        tool_handler = module.JjMailboxMCPTools(settings)
        server = module.build_server(settings)

        assert list(server.tools.keys()) == expected_names, server.tools.keys()
        assert server.name == "jj-mailbox", server.name

        calls = []
        read_responses = [
            (json.dumps({"from": "alice", "to": "bob", "subject": "MCP smoke test"}), "", 0),
            ("", "", 1),
        ]

        def fake_run_cli(cmd_args):
            calls.append(cmd_args)
            if cmd_args[1] == "send":
                return ("msg-1234", "", 0)
            if cmd_args[1] == "inbox":
                return ("Inbox empty." if cmd_args[-1] == "alice" else "From: alice  Subject: MCP smoke test", "", 0)
            if cmd_args[1] == "read":
                return read_responses.pop(0)
            if cmd_args[1] == "status":
                return ("🟢 alice\n🟢 bob", "", 0)
            raise AssertionError(f"Unexpected command: {cmd_args}")

        tool_handler._run_cli = fake_run_cli  # type: ignore[method-assign]

        send_result = tool_handler.send_message(
            to="Bob",
            subject="MCP smoke test",
            body="Hello from the MCP wrapper.",
        )
        assert send_result == "Message sent. ID: msg-1234", send_result
        assert calls[-1][0:3] == [BIN, "send", "bob"], calls[-1]

        check_before = tool_handler.check_inbox()
        assert check_before == "Inbox empty.", check_before

        bob_handler = module.JjMailboxMCPTools(
            module.ServerSettings(
                bin_path=module.Path(BIN),
                repo_path=module.Path(repo),
                agent_name="bob",
            )
        )
        bob_handler._run_cli = fake_run_cli  # type: ignore[method-assign]

        inbox_result = bob_handler.check_inbox()
        assert "MCP smoke test" in inbox_result, inbox_result

        read_result = bob_handler.read_inbox()
        payload = json.loads(read_result)
        assert payload["from"] == "alice", payload
        assert payload["to"] == "bob", payload
        assert payload["subject"] == "MCP smoke test", payload

        empty_result = bob_handler.read_inbox()
        assert empty_result == "Inbox is empty.", empty_result

        status_result = tool_handler.get_status()
        assert "alice" in status_result and "bob" in status_result, status_result

        artifact_result = tool_handler.write_artifact(
            filename="mcp/result.txt",
            content="MCP server artifact coverage.\n",
        )
        assert artifact_result == "Artifact written: shared/artifacts/mcp/result.txt", artifact_result
        with open(os.path.join(repo, "shared", "artifacts", "mcp", "result.txt")) as f:
            assert f.read() == "MCP server artifact coverage.\n"

        try:
            tool_handler.write_artifact("../escape.txt", "nope")
        except ValueError:
            pass
        else:
            raise AssertionError("Expected write_artifact to reject path traversal")

        print("✅ MCP wrapper regression tests passed")


if __name__ == "__main__":
    main()

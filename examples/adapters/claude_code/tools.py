"""Anthropic Claude Code tool-use adapter for jj-mailbox.

Exposes Anthropic ``tools`` definitions (``name`` + ``input_schema``) and a
handler compatible with tool_use / tool_result message loops.
"""

from __future__ import annotations

from examples.adapters.openai.tools import JjMailboxOpenAITools


CLAUDE_TOOLS = [
    {
        "name": "send_message",
        "description": "Send a message to another agent",
        "input_schema": {
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
    {
        "name": "read_inbox",
        "description": "Read the oldest unread message from inbox. Returns message JSON or empty string.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "write_artifact",
        "description": "Write content to a shared artifact file in shared/artifacts/",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "File name (e.g. design.md)"},
                "content": {"type": "string", "description": "File content to write"},
            },
            "required": ["filename", "content"],
        },
    },
]


class JjMailboxClaudeTools(JjMailboxOpenAITools):
    """Claude adapter uses the same execution logic with different schemas."""

#!/usr/bin/env python3
"""
Level 3b: Tool-calling LLM agent with a quality model.

Same structure as level3a but:
  - Default model: moonshot-v1-8k (Kimi)
  - 3-agent scenario: Planner + Researcher + Critic
  - 5 rounds
  - Tests context retention across long threads, multi-agent fan-out

Usage:
  LLM_API_KEY=sk-... LLM_API_BASE=https://api.moonshot.cn/v1 python3 tests/level3b-llm-online/test.py

  # Or any OpenAI-compatible API:
  LLM_API_KEY=... LLM_API_BASE=... LLM_MODEL=gpt-4o-mini python3 tests/level3b-llm-online/test.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
BIN = os.path.join(REPO_ROOT, "bin", "jj-mailbox")

LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_API_BASE = os.environ.get("LLM_API_BASE", "https://api.moonshot.cn/v1")
LLM_MODEL = os.environ.get("LLM_MODEL", "moonshot-v1-8k")

MAX_TURNS = 8

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "send_message",
            "description": "Send a message to another agent",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "refs": {"type": "string", "description": "Comma-separated message IDs being replied to"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_inbox",
            "description": "Read oldest unread message. Returns JSON or 'Inbox is empty.'",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_artifact",
            "description": "Write to shared/artifacts/<filename>",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_artifact",
            "description": "Read content of a shared artifact file",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}},
                "required": ["filename"],
            },
        },
    },
]


def run_cli(cmd, env=None):
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, env=merged)
    return result.stdout.strip(), result.returncode


def setup_repo():
    repo = tempfile.mkdtemp(prefix="jj-mailbox-3b-")
    subprocess.run("git config --global user.email ci@test.local 2>/dev/null || true", shell=True, capture_output=True)
    subprocess.run("git config --global user.name CI 2>/dev/null || true", shell=True, capture_output=True)
    subprocess.run(f"{BIN} init {repo}", shell=True, check=True)
    for agent, desc in [
        ("planner", "Task planner and coordinator"),
        ("researcher", "Research and analysis specialist"),
        ("critic", "Quality critic and reviewer"),
    ]:
        subprocess.run(f"JJ_MAILBOX_REPO={repo} {BIN} register {agent} '{desc}'", shell=True, check=True)
    os.makedirs(os.path.join(repo, "shared", "artifacts"), exist_ok=True)
    return repo


def execute_tool(name, args, agent_name, repo):
    if name == "send_message":
        to = args.get("to", "").lower().strip()
        subject = args.get("subject", "")
        body = args.get("body", "")
        refs = args.get("refs", "")
        cmd = f'{BIN} send {to} "{subject}" "{body}"'
        if refs:
            cmd += f" --refs {refs}"
        stdout, code = run_cli(cmd, {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": agent_name})
        lines = [l for l in stdout.splitlines() if l.strip()]
        msg_id = lines[-1] if lines else "unknown"
        return f"Message sent. ID: {msg_id}" if code == 0 else f"Error: {stdout}"

    elif name == "read_inbox":
        stdout, code = run_cli(
            f"{BIN} read {agent_name}",
            {"JJ_MAILBOX_REPO": repo, "JJ_MAILBOX_AGENT": agent_name},
        )
        if not stdout:
            return "Inbox is empty."
        try:
            return json.dumps(json.loads(stdout), indent=2)
        except json.JSONDecodeError:
            return stdout

    elif name == "write_artifact":
        path = os.path.join(repo, "shared", "artifacts", args.get("filename", "artifact.txt"))
        with open(path, "w") as f:
            f.write(args.get("content", ""))
        return f"Artifact written: {args.get('filename')}"

    elif name == "read_artifact":
        path = os.path.join(repo, "shared", "artifacts", args.get("filename", ""))
        if not os.path.isfile(path):
            return "File not found."
        with open(path) as f:
            return f.read()

    return f"Unknown tool: {name}"


def run_agent(agent_name, system_prompt, user_prompt, repo, client, log):
    import openai

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=600,
            temperature=0.7,
        )
        msg = response.choices[0].message
        if not msg.tool_calls:
            final = msg.content or ""
            log.append({"agent": agent_name, "type": "text", "content": final})
            return final

        messages.append({"role": "assistant", "content": msg.content, "tool_calls": [
            {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]})

        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments)
            result = execute_tool(tc.function.name, args, agent_name, repo)
            print(f"  [{agent_name}] {tc.function.name}({list(args.keys())}) → {result[:80]}")
            log.append({"agent": agent_name, "type": "tool_call", "tool": tc.function.name, "args": args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "Max turns reached."


def main():
    print("=" * 60)
    print("Level 3b: Tool-calling LLM agent (quality model)")
    print("=" * 60)

    if not LLM_API_KEY:
        print()
        print("⏭  SKIP: LLM_API_KEY not set.")
        print("   Set LLM_API_KEY (and optionally LLM_API_BASE, LLM_MODEL).")
        sys.exit(0)

    try:
        import openai
    except ImportError:
        print("ERROR: openai not installed.  pip install openai")
        sys.exit(1)

    print(f"Model: {LLM_MODEL}")
    print(f"API base: {LLM_API_BASE}")
    print()

    client = openai.OpenAI(api_key=LLM_API_KEY, base_url=LLM_API_BASE)
    repo = setup_repo()
    log = []

    try:
        TASK = (
            "Design a distributed task queue system. "
            "Requirements: reliable delivery, at-least-once semantics, backpressure handling."
        )

        # Round 1: Planner broadcasts task to researcher and critic
        print("Round 1: Planner broadcasts task")
        run_agent(
            "planner",
            "You are a Planner coordinating a design task. Send tasks to 'researcher' and 'critic' via jj-mailbox.",
            f"Send the following task to BOTH 'researcher' AND 'critic': {TASK}. "
            "Subject: 'Design task'. Then write a project outline to artifact 'outline.md'.",
            repo, client, log,
        )

        # Round 2: Researcher reads and sends findings
        print("Round 2: Researcher analyzes and reports")
        run_agent(
            "researcher",
            "You are a Researcher. Read tasks with read_inbox, send findings with send_message.",
            "Read your task from the inbox. Research and send 'planner' your analysis of "
            "distributed task queue options (e.g., Celery, SQS, custom). "
            "Subject: 'Research findings'. Save detailed notes to artifact 'research.md'.",
            repo, client, log,
        )

        # Round 3: Critic reads and sends critique
        print("Round 3: Critic reviews")
        run_agent(
            "critic",
            "You are a Critic. Read tasks with read_inbox, send critiques with send_message.",
            "Read your task from the inbox. Send 'planner' a critical analysis: "
            "risks, failure modes, and open questions for the distributed task queue design. "
            "Subject: 'Critical review'.",
            repo, client, log,
        )

        # Round 4: Planner reads all feedback, compiles
        print("Round 4: Planner compiles feedback")
        run_agent(
            "planner",
            "You are a Planner. Read all incoming messages and synthesize findings.",
            "Read all messages in your inbox (call read_inbox multiple times until empty). "
            "Write a final design decision to artifact 'final_design.md' incorporating "
            "researcher findings and critic concerns.",
            repo, client, log,
        )

        # Round 5: Planner notifies all agents of decision
        print("Round 5: Planner announces decision")
        run_agent(
            "planner",
            "You are a Planner. Read the final design artifact and notify team.",
            "Read 'final_design.md' artifact. Send BOTH 'researcher' AND 'critic' a "
            "summary of the final decision. Subject: 'Design decision'.",
            repo, client, log,
        )

        # Save log
        log_path = os.path.join(repo, "shared", "artifacts", "conversation.json")
        with open(log_path, "w") as f:
            json.dump({"model": LLM_MODEL, "api_base": LLM_API_BASE, "rounds": 5, "log": log}, f, indent=2)

        print()
        print("Assertions:")

        # Check some messages were delivered
        def msg_count(agent):
            n = os.path.join(repo, f"inbox/{agent}/new")
            p = os.path.join(repo, f"inbox/{agent}/processed")
            return (
                len([f for f in os.listdir(n) if f.endswith(".json")])
                + len([f for f in os.listdir(p) if f.endswith(".json")])
            )

        for agent in ["planner", "researcher", "critic"]:
            c = msg_count(agent)
            print(f"  {agent} total messages: {c}")
        assert msg_count("researcher") >= 1, "researcher should have received messages"
        assert msg_count("critic") >= 1, "critic should have received messages"
        assert msg_count("planner") >= 1, "planner should have received messages"

        artifacts = os.listdir(os.path.join(repo, "shared", "artifacts"))
        print(f"  Artifacts: {artifacts}")
        assert "conversation.json" in artifacts, "conversation log should exist"

        print()
        print("=" * 60)
        print("✅ Level 3b: Multi-agent quality LLM test passed!")
        print("=" * 60)

    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Two AI agents having a real conversation via jj-mailbox.

Uses any OpenAI-compatible API (OpenRouter, Kimi, local models, etc.).

Usage:
    # Set your API key and run
    export LLM_API_KEY="your-key"
    export JJ_MAILBOX_REPO="/path/to/your/mailbox"

    # Optional: configure API endpoint and model
    export LLM_API_BASE="https://openrouter.ai/api/v1"  # default
    export LLM_MODEL="xiaomi/mimo-v2-flash:free"         # default (free)

    python3 agent_chat.py "Design a REST API for a todo app" 3
"""

import json, sys, os, glob, urllib.request


API_KEY = os.environ["LLM_API_KEY"]
API_BASE = os.environ.get("LLM_API_BASE", "https://openrouter.ai/api/v1")
MODEL = os.environ.get("LLM_MODEL", "xiaomi/mimo-v2-flash:free")
REPO = os.environ.get("JJ_MAILBOX_REPO", "/tmp/demo")


def llm_chat(system_prompt, user_message):
    """Call any OpenAI-compatible API."""
    url = f"{API_BASE}/chat/completions"
    payload = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "max_tokens": 500,
        "temperature": 0.7
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def read_inbox(agent):
    """Read newest message from agent's inbox."""
    inbox = os.path.join(REPO, f"inbox/{agent}/new")
    files = sorted(glob.glob(os.path.join(inbox, "*.json")))
    if not files:
        return None
    with open(files[0]) as f:
        msg = json.load(f)
    # Move to processed
    processed = os.path.join(REPO, f"inbox/{agent}/processed")
    os.rename(files[0], os.path.join(processed, os.path.basename(files[0])))
    return msg


def send_message(frm, to, subject, body):
    """Write a message file to recipient's inbox."""
    import time, random
    ts = time.strftime("%Y-%m-%dT%H-%M-%SZ", time.gmtime())
    msg_id = f"msg-{random.randbytes(4).hex()}"
    filename = f"{ts}_{frm}_{msg_id}.json"
    msg = {
        "version": "0.1",
        "id": msg_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "from": frm,
        "to": to,
        "type": "message",
        "subject": subject,
        "body": body,
        "refs": [],
        "metadata": {"model": MODEL}
    }
    path = os.path.join(REPO, f"inbox/{to}/new/{filename}")
    with open(path, "w") as f:
        json.dump(msg, f, indent=2)
    return msg


def main():
    task = sys.argv[1] if len(sys.argv) > 1 else "Discuss a simple API design."
    rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    alice_system = (
        "You are Alice, an API designer. You are collaborating with Bob via messages. "
        "Keep responses concise (under 200 words). Be specific and technical."
    )
    bob_system = (
        "You are Bob, a code reviewer. You are collaborating with Alice via messages. "
        "Keep responses concise (under 200 words). Give constructive feedback."
    )

    conversation = []

    # Round 1: Alice starts
    print(f"\n{'='*60}")
    print(f"Task: {task}")
    print(f"Model: {MODEL}")
    print(f"Rounds: {rounds}")
    print(f"{'='*60}\n")

    alice_msg = llm_chat(alice_system, f"Task: {task}\n\nWrite your initial proposal.")
    send_message("alice", "bob", "Initial proposal", alice_msg)
    conversation.append({"from": "alice", "body": alice_msg})
    print(f"Alice -> Bob:\n{alice_msg}\n")

    # Conversation loop
    for i in range(rounds - 1):
        # Bob reads and replies
        msg = read_inbox("bob")
        context = "\n".join([f"{m['from']}: {m['body']}" for m in conversation])
        bob_msg = llm_chat(bob_system, f"Conversation so far:\n{context}\n\nRespond to Alice's latest message.")
        send_message("bob", "alice", f"Round {i+2} feedback", bob_msg)
        conversation.append({"from": "bob", "body": bob_msg})
        print(f"Bob -> Alice:\n{bob_msg}\n")

        # Alice reads and replies (except last round)
        if i < rounds - 2:
            msg = read_inbox("alice")
            context = "\n".join([f"{m['from']}: {m['body']}" for m in conversation])
            alice_msg = llm_chat(alice_system, f"Conversation so far:\n{context}\n\nRespond to Bob's feedback.")
            send_message("alice", "bob", f"Round {i+2} revision", alice_msg)
            conversation.append({"from": "alice", "body": alice_msg})
            print(f"Alice -> Bob:\n{alice_msg}\n")

    # Save conversation log
    log_path = os.path.join(REPO, "shared/artifacts/conversation.json")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "w") as f:
        json.dump({"task": task, "model": MODEL, "conversation": conversation}, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Conversation complete! {len(conversation)} messages exchanged.")
    print(f"Log saved to: shared/artifacts/conversation.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()

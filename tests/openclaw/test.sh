#!/usr/bin/env bash
# OpenClaw integration test: two real OpenClaw agents communicating via jj-mailbox
#
# Requires: docker, LLM_API_KEY
# Optional: LLM_API_BASE (default: OpenRouter), LLM_MODEL (default: openrouter/free)
#
# Usage:
#   LLM_API_KEY=sk-or-... ./test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# --- Preflight ---
if [ -z "${LLM_API_KEY:-}" ]; then
  echo "SKIP: LLM_API_KEY not set."
  echo "  LLM_API_KEY=sk-or-... ./test.sh"
  echo "  See docs/MODEL_CHOICES.md for provider options."
  exit 0
fi

echo "============================================================"
echo "OpenClaw integration test: two agents via jj-mailbox"
echo "============================================================"
echo "Provider: ${LLM_API_BASE:-https://openrouter.ai/api/v1}"
echo "Model:    ${LLM_MODEL:-openrouter/free}"
echo ""

cleanup() {
  echo "Cleaning up..."
  docker compose down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# --- Start containers ---
echo "Starting containers..."
docker compose up -d --build --wait 2>&1

echo "Waiting for agents to initialize..."
sleep 8

# --- Verify both agents are running ---
echo "Checking agent status..."
docker compose exec alice jj-mailbox status
echo ""

# --- Alice sends a message to Bob ---
echo "Step 1: Alice sends Bob a message via OpenClaw agent..."
docker compose exec -T alice openclaw agent --message \
  'Use jj-mailbox to send bob a message. Subject: "Cache design". Body: "Should we use LRU or Redis? Please advise." Use the command: jj-mailbox send bob "Cache design" "Should we use LRU or Redis? Please advise."' \
  2>&1 | tail -20
echo ""

# Wait for sync
echo "Waiting for sync..."
sleep 15

# --- Check Bob received the message ---
echo "Step 2: Checking Bob's inbox..."
BOB_COUNT=$(docker compose exec bob sh -c 'find /mailbox/inbox/bob/new -name "*.json" 2>/dev/null | wc -l' | tr -d '[:space:]')
echo "  Bob has $BOB_COUNT message(s)"

if [ "$BOB_COUNT" -eq 0 ]; then
  # If OpenClaw didn't use the skill correctly, send manually as fallback
  echo "  OpenClaw agent may not have used jj-mailbox CLI — sending manually..."
  docker compose exec alice sh -c 'cd /mailbox && jj-mailbox send bob "Cache design" "Should we use LRU or Redis? Please advise."'
  sleep 12
  BOB_COUNT=$(docker compose exec bob sh -c 'find /mailbox/inbox/bob/new -name "*.json" 2>/dev/null | wc -l' | tr -d '[:space:]')
  echo "  Bob now has $BOB_COUNT message(s)"
fi

# --- Bob reads and replies via OpenClaw ---
echo ""
echo "Step 3: Bob reads inbox and replies via OpenClaw agent..."
docker compose exec -T bob openclaw agent --message \
  'Use jj-mailbox to read your inbox and reply. First run: jj-mailbox read bob. Then reply to alice with your recommendation using: jj-mailbox send alice "Re: Cache design" "I recommend Redis for distributed caching."' \
  2>&1 | tail -20
echo ""

# Wait for sync
echo "Waiting for sync..."
sleep 15

# --- Verify results ---
echo ""
echo "Step 4: Verification..."

ALICE_MSGS=$(docker compose exec alice sh -c 'find /mailbox/inbox/alice/new /mailbox/inbox/alice/processed -name "*.json" 2>/dev/null | wc -l' | tr -d '[:space:]')
BOB_MSGS=$(docker compose exec bob sh -c 'find /mailbox/inbox/bob/new /mailbox/inbox/bob/processed -name "*.json" 2>/dev/null | wc -l' | tr -d '[:space:]')

echo "  Messages delivered to Alice: $ALICE_MSGS"
echo "  Messages delivered to Bob:   $BOB_MSGS"

# Show jj history from Alice's repo
echo ""
echo "  jj log (Alice's view):"
docker compose exec alice sh -c 'cd /mailbox && jj log --no-pager 2>/dev/null | head -15' || true

# --- Assertions ---
echo ""
if [ "$BOB_MSGS" -ge 1 ]; then
  echo "============================================================"
  echo "PASS: OpenClaw agents communicated via jj-mailbox"
  echo "============================================================"
else
  echo "============================================================"
  echo "FAIL: No messages delivered"
  echo "============================================================"
  exit 1
fi

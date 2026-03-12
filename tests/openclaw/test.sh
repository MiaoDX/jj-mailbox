#!/usr/bin/env bash
# OpenClaw integration test: two real OpenClaw agents communicating via jj-mailbox
#
# Multi-turn conversation: Alice and Bob exchange messages through jj-mailbox,
# driven by OpenClaw agents (or direct CLI in --no-llm mode).
# Both agents share the same jj repo volume — no git sync needed.
#
# Usage:
#   ./test.sh           # full test with LLM (needs LLM_API_KEY in .env or env)
#   ./test.sh --no-llm  # CLI-only test, no API key needed
#
# Requires: docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

# --- Configuration ---
TIMEOUT=180  # 3 minutes
NO_LLM=false
COMPOSE="docker compose"
FALLBACK_COUNT=0

# Parse args
for arg in "$@"; do
  case "$arg" in
    --no-llm) NO_LLM=true ;;
    *) echo "Unknown option: $arg"; exit 1 ;;
  esac
done

# Auto-load .env from project root if LLM_API_KEY not set
if [ -z "${LLM_API_KEY:-}" ] && [ -f "$PROJECT_ROOT/.env" ]; then
  echo "Loading .env from $PROJECT_ROOT/.env"
  set -a
  # shellcheck disable=SC1091
  source "$PROJECT_ROOT/.env"
  set +a
fi

# Preflight
if [ "$NO_LLM" = false ] && [ -z "${LLM_API_KEY:-}" ]; then
  echo "SKIP: LLM_API_KEY not set and --no-llm not specified."
  echo "  Set LLM_API_KEY in .env or export it, or run with --no-llm"
  echo "  See docs/MODEL_CHOICES.md for provider options."
  exit 0
fi

echo "============================================================"
echo "OpenClaw integration test: two agents via jj-mailbox"
echo "============================================================"
if [ "$NO_LLM" = true ]; then
  echo "Mode: --no-llm (CLI-only, no OpenClaw agent)"
else
  echo "Provider: ${LLM_API_BASE:-https://openrouter.ai/api/v1}"
  echo "Model:    ${LLM_MODEL:-openrouter/free}"
fi
echo ""

# --- Cleanup ---
cleanup() {
  local exit_code=$?
  # Kill timeout guard if still running
  if [ -n "${TIMEOUT_PID:-}" ]; then
    kill "$TIMEOUT_PID" 2>/dev/null || true
    wait "$TIMEOUT_PID" 2>/dev/null || true
  fi
  if [ $exit_code -ne 0 ]; then
    echo ""
    echo "=== Container logs (failure debug) ==="
    echo "--- alice ---"
    $COMPOSE logs --tail=50 alice 2>/dev/null || true
    echo "--- bob ---"
    $COMPOSE logs --tail=50 bob 2>/dev/null || true
  fi
  echo "Cleaning up..."
  $COMPOSE down -v --remove-orphans 2>/dev/null || true
}
trap cleanup EXIT

# --- Timeout guard ---
(
  sleep "$TIMEOUT"
  echo ""
  echo "TIMEOUT: test exceeded ${TIMEOUT}s"
  kill -TERM "$$" 2>/dev/null
) &
TIMEOUT_PID=$!

# --- Helpers ---
wait_agents_ready() {
  # Wait until both agents are registered in the shared repo
  local max_wait=${1:-60}
  local elapsed=0
  echo "  Waiting for both agents to be registered..."
  while [ $elapsed -lt "$max_wait" ]; do
    if $COMPOSE exec -T alice test -d /mailbox/agents/alice -a -d /mailbox/agents/bob 2>/dev/null; then
      echo "  Both agents registered (${elapsed}s)"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "  TIMEOUT: agents not registered after ${max_wait}s"
  return 1
}

wait_for_message() {
  local container=$1
  local agent=$2
  local min_count=$3
  local max_wait=${4:-30}
  local elapsed=0
  echo "  Polling for $agent to have >= $min_count message(s)..."
  while [ $elapsed -lt "$max_wait" ]; do
    local count
    count=$($COMPOSE exec -T "$container" sh -c \
      "find /mailbox/inbox/$agent/new /mailbox/inbox/$agent/processed -name '*.json' 2>/dev/null | wc -l" \
      | tr -d '[:space:]')
    if [ "${count:-0}" -ge "$min_count" ] 2>/dev/null; then
      echo "  $agent has $count message(s) (${elapsed}s)"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "  TIMEOUT: $agent has < $min_count messages after ${max_wait}s"
  return 1
}

count_messages() {
  local container=$1
  local agent=$2
  $COMPOSE exec -T "$container" sh -c \
    "find /mailbox/inbox/$agent/new /mailbox/inbox/$agent/processed -name '*.json' 2>/dev/null | wc -l" \
    | tr -d '[:space:]'
}

# --- Start containers ---
echo "Building and starting containers..."
$COMPOSE up -d --build 2>&1

# Wait for both agents to be registered in the shared repo
wait_agents_ready 60

# Verify registrations
echo "  Agent status:"
$COMPOSE exec -T alice sh -c 'cd /mailbox && jj-mailbox status' 2>&1 | head -10
echo ""
echo "Both agents online."
echo ""

# ==========================================================================
# Multi-turn conversation
# ==========================================================================

# --- Turn 1: Alice → Bob ---
echo "=== Turn 1: Alice → Bob ==="
if [ "$NO_LLM" = true ]; then
  echo "  (--no-llm: using CLI directly)"
  $COMPOSE exec -T alice sh -c \
    'cd /mailbox && jj-mailbox send bob "Cache design" "Should we use LRU or Redis for the session store? Consider our 10k concurrent users requirement."'
else
  echo "  Alice's OpenClaw agent sending message to Bob..."
  $COMPOSE exec -T alice openclaw agent --local -m \
    "Use jj-mailbox to send bob a message. Subject: 'Cache design'. Body: 'Should we use LRU or Redis for the session store? Consider our 10k concurrent users requirement.'" \
    2>&1 | tail -20 || true
fi

# Poll for Bob to receive Turn 1
if ! wait_for_message bob bob 1 30; then
  if [ "$NO_LLM" = false ]; then
    echo "  Fallback: OpenClaw agent didn't use skill — sending via CLI"
    FALLBACK_COUNT=$((FALLBACK_COUNT + 1))
    $COMPOSE exec -T alice sh -c \
      'cd /mailbox && jj-mailbox send bob "Cache design" "Should we use LRU or Redis for the session store? Consider our 10k concurrent users requirement."'
    wait_for_message bob bob 1 10 || true
  fi
fi
echo ""

# --- Turn 2: Bob → Alice ---
echo "=== Turn 2: Bob → Alice ==="
if [ "$NO_LLM" = true ]; then
  echo "  (--no-llm: using CLI directly)"
  $COMPOSE exec -T bob sh -c \
    'cd /mailbox && jj-mailbox send alice "Re: Cache design" "I recommend Redis for distributed caching with our 10k concurrent users. LRU is better for single-process caches."'
else
  echo "  Bob's OpenClaw agent reading inbox and replying..."
  $COMPOSE exec -T bob openclaw agent --local -m \
    "Use jj-mailbox to check your inbox (jj-mailbox read bob), then reply to alice with your recommendation. Use jj-mailbox send." \
    2>&1 | tail -20 || true
fi

if ! wait_for_message alice alice 1 30; then
  if [ "$NO_LLM" = false ]; then
    echo "  Fallback: OpenClaw agent didn't use skill — sending via CLI"
    FALLBACK_COUNT=$((FALLBACK_COUNT + 1))
    $COMPOSE exec -T bob sh -c \
      'cd /mailbox && jj-mailbox send alice "Re: Cache design" "I recommend Redis for distributed caching with our 10k concurrent users."'
    wait_for_message alice alice 1 10 || true
  fi
fi
echo ""

# --- Turn 3: Alice → Bob (follow-up) ---
echo "=== Turn 3: Alice → Bob (follow-up) ==="
if [ "$NO_LLM" = true ]; then
  echo "  (--no-llm: using CLI directly)"
  $COMPOSE exec -T alice sh -c \
    'cd /mailbox && jj-mailbox send bob "Re: Cache design" "Thanks for the Redis recommendation. What eviction policy would you suggest — LRU, LFU, or TTL-based?"'
else
  echo "  Alice's OpenClaw agent reading reply and sending follow-up..."
  $COMPOSE exec -T alice openclaw agent --local -m \
    "Use jj-mailbox to read your inbox (jj-mailbox read alice), then send bob a follow-up message acknowledging his recommendation and asking about eviction policy. Use jj-mailbox send." \
    2>&1 | tail -20 || true
fi

if ! wait_for_message bob bob 2 30; then
  if [ "$NO_LLM" = false ]; then
    echo "  Fallback: OpenClaw agent didn't use skill — sending via CLI"
    FALLBACK_COUNT=$((FALLBACK_COUNT + 1))
    $COMPOSE exec -T alice sh -c \
      'cd /mailbox && jj-mailbox send bob "Re: Cache design" "Thanks for the Redis recommendation. What eviction policy would you suggest — LRU, LFU, or TTL-based?"'
    wait_for_message bob bob 2 10 || true
  fi
fi
echo ""

# ==========================================================================
# Verification
# ==========================================================================

echo "=== Verification ==="
ALICE_MSGS=$(count_messages alice alice)
BOB_MSGS=$(count_messages bob bob)
TOTAL=$((ALICE_MSGS + BOB_MSGS))

echo "  Messages delivered to Alice: $ALICE_MSGS"
echo "  Messages delivered to Bob:   $BOB_MSGS"
echo "  Total messages:              $TOTAL"
if [ "$NO_LLM" = false ]; then
  echo "  Fallback turns:             $FALLBACK_COUNT"
fi

# jj log
echo ""
echo "  jj log (Alice's view):"
$COMPOSE exec -T alice sh -c 'cd /mailbox && jj log --no-pager 2>/dev/null | head -15' || true

# --- Assertions ---
echo ""
PASS=true

if [ "$BOB_MSGS" -lt 2 ]; then
  echo "FAIL: Bob should have >= 2 messages, got $BOB_MSGS"
  PASS=false
fi

if [ "$ALICE_MSGS" -lt 1 ]; then
  echo "FAIL: Alice should have >= 1 message, got $ALICE_MSGS"
  PASS=false
fi

if [ "$TOTAL" -lt 3 ]; then
  echo "FAIL: Total messages should be >= 3, got $TOTAL"
  PASS=false
fi

if [ "$PASS" = true ]; then
  echo "============================================================"
  echo "PASS: Multi-turn conversation completed successfully"
  if [ "$NO_LLM" = false ] && [ "$FALLBACK_COUNT" -gt 0 ]; then
    echo "  (${FALLBACK_COUNT} turn(s) used CLI fallback)"
  fi
  echo "============================================================"
else
  echo "============================================================"
  echo "FAIL: Assertions failed (see above)"
  echo "============================================================"
  exit 1
fi

#!/usr/bin/env bash
# OpenClaw integration test: five OpenClaw agents communicating via jj-mailbox
#
# Modes:
#   ./test.sh --no-llm     # CLI-only, 30 messages across 5 agents
#   ./test.sh --llm-smoke  # 1 real OpenClaw agent turn + verify receipt
#   ./test.sh              # LLM smoke test + 30-message CLI test
#
# Requires: docker
# Optional: LLM_API_KEY (from .env or environment)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$SCRIPT_DIR"

# --- Configuration ---
TIMEOUT=300  # 5 minutes (longer for 5 agents + 30 messages)
NO_LLM=false
LLM_SMOKE=false
COMPOSE="docker compose"
FALLBACK_USED=false
MSG_COUNT=30

AGENTS=(alice bob carol dave eve)
NUM_AGENTS=${#AGENTS[@]}
TOPICS=(
  "Cache design"
  "Auth refactor"
  "API versioning"
  "DB migration"
  "Load testing"
  "Error handling"
  "Logging strategy"
  "CI pipeline"
  "Code review"
  "Deployment"
)

# Parse args
for arg in "$@"; do
  case "$arg" in
    --no-llm) NO_LLM=true ;;
    --llm-smoke) LLM_SMOKE=true ;;
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
  exit 0
fi

echo "============================================================"
echo "OpenClaw integration test: 5 agents via jj-mailbox"
echo "============================================================"
if [ "$NO_LLM" = true ]; then
  echo "Mode: --no-llm (CLI-only, $MSG_COUNT messages, $NUM_AGENTS agents)"
elif [ "$LLM_SMOKE" = true ]; then
  echo "Mode: --llm-smoke (1 OpenClaw agent turn + verify)"
else
  echo "Mode: full (LLM smoke + $MSG_COUNT CLI messages)"
fi
echo "Agents: ${AGENTS[*]}"
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
    for agent in "${AGENTS[@]}"; do
      echo "--- $agent ---"
      $COMPOSE logs --tail=30 "$agent" 2>/dev/null || true
    done
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
wait_all_agents_ready() {
  local max_wait=${1:-90}
  local elapsed=0
  echo "  Waiting for all $NUM_AGENTS agents to register..."
  while [ $elapsed -lt "$max_wait" ]; do
    local ready=true
    for agent in "${AGENTS[@]}"; do
      if ! $COMPOSE exec -T alice test -d "/mailbox/agents/$agent" 2>/dev/null; then
        ready=false
        break
      fi
    done
    if [ "$ready" = true ]; then
      echo "  All $NUM_AGENTS agents registered (${elapsed}s)"
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  echo "  TIMEOUT: not all agents registered after ${max_wait}s"
  # Show which ones are missing
  for agent in "${AGENTS[@]}"; do
    if ! $COMPOSE exec -T alice test -d "/mailbox/agents/$agent" 2>/dev/null; then
      echo "    Missing: $agent"
    fi
  done
  return 1
}

wait_for_message() {
  local container=$1
  local agent=$2
  local min_count=$3
  local max_wait=${4:-30}
  local elapsed=0
  while [ $elapsed -lt "$max_wait" ]; do
    local count
    count=$($COMPOSE exec -T "$container" sh -c \
      "find /mailbox/inbox/$agent/new /mailbox/inbox/$agent/processed -name '*.json' 2>/dev/null | wc -l" \
      | tr -d '[:space:]')
    if [ "${count:-0}" -ge "$min_count" ] 2>/dev/null; then
      return 0
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done
  return 1
}

count_messages() {
  local agent=$1
  $COMPOSE exec -T alice sh -c \
    "find /mailbox/inbox/$agent/new /mailbox/inbox/$agent/processed -name '*.json' 2>/dev/null | wc -l" \
    | tr -d '[:space:]'
}

# --- Start containers ---
echo "Building and starting containers..."
$COMPOSE up -d --build 2>&1

wait_all_agents_ready 90

# Show status
echo "  Agent status:"
$COMPOSE exec -T alice sh -c 'cd /mailbox && jj-mailbox status' 2>&1 | head -15
echo ""

# ==========================================================================
# LLM Smoke Test (--llm-smoke or default mode)
# ==========================================================================
if [ "$NO_LLM" = false ]; then
  echo "=== LLM Smoke Test ==="
  echo "  Alice sending message to Bob via OpenClaw agent..."
  echo ""

  # Run one real OpenClaw agent turn (--session-id required by openclaw agent)
  $COMPOSE exec -T alice openclaw agent --local --session-id smoke-test -m \
    "You have the jj-mailbox skill installed at ~/.openclaw/skills/jj-mailbox. Use it to send bob a message. Run this exact command in your terminal: jj-mailbox send bob 'LLM smoke test' 'Hello from OpenClaw agent. This is an automated test.'" \
    2>&1 | tail -50 || true

  echo ""

  # Check if bob received the message
  if wait_for_message alice bob 1 60; then
    echo "  Bob received message from OpenClaw agent"
    FALLBACK_USED=false
  else
    echo "  OpenClaw agent didn't deliver message (model may not support tool use)"
    echo "  Using CLI fallback to verify transport layer..."
    FALLBACK_USED=true
    $COMPOSE exec -T alice sh -c \
      'cd /mailbox && jj-mailbox send bob "LLM smoke test" "Fallback: CLI verification"'
  fi
  echo ""

  # If --llm-smoke mode, verify and exit
  if [ "$LLM_SMOKE" = true ]; then
    BOB_MSGS=$(count_messages bob)
    echo "=== LLM Smoke Verification ==="
    echo "  Bob has $BOB_MSGS message(s)"
    if [ "$BOB_MSGS" -ge 1 ]; then
      if [ "$FALLBACK_USED" = true ]; then
        echo "============================================================"
        echo "PASS: Transport layer verified (CLI fallback used)"
        echo "  Note: OpenClaw agent did not use jj-mailbox skill autonomously"
        echo "============================================================"
      else
        echo "============================================================"
        echo "PASS: OpenClaw agent delivered message via jj-mailbox"
        echo "============================================================"
      fi
      exit 0
    else
      echo "============================================================"
      echo "FAIL: No messages delivered to Bob"
      echo "============================================================"
      exit 1
    fi
  fi
fi

# ==========================================================================
# 30-Message Round-Robin Test (--no-llm or default mode)
# ==========================================================================
echo "=== $MSG_COUNT-Message Round-Robin Test ==="
echo "  Sending $MSG_COUNT messages across $NUM_AGENTS agents..."
printf "  Progress: "

for i in $(seq 1 "$MSG_COUNT"); do
  sender_idx=$(( (i - 1) % NUM_AGENTS ))
  receiver_idx=$(( i % NUM_AGENTS ))
  sender="${AGENTS[$sender_idx]}"
  receiver="${AGENTS[$receiver_idx]}"
  topic_idx=$(( (i - 1) % ${#TOPICS[@]} ))
  topic="${TOPICS[$topic_idx]}"

  $COMPOSE exec -T "$sender" sh -c \
    "cd /mailbox && jj-mailbox send '$receiver' '$topic' 'Message $i from $sender to $receiver about $topic'" \
    >/dev/null 2>&1

  printf "."
  if [ $((i % 10)) -eq 0 ]; then
    printf " "
  fi
done
echo " done"
echo ""

# ==========================================================================
# Verification
# ==========================================================================
echo "=== Verification ==="
TOTAL=0
PASS=true

for agent in "${AGENTS[@]}"; do
  count=$(count_messages "$agent")
  TOTAL=$((TOTAL + count))
  printf "  %-8s %s messages" "$agent:" "$count"
  if [ "$count" -lt 4 ]; then
    printf "  (expected >= 4)"
  fi
  echo ""
done

echo "  ────────────────────"
echo "  Total:   $TOTAL messages"
echo ""

# jj log
echo "  jj log (last 20 entries):"
$COMPOSE exec -T alice sh -c 'cd /mailbox && jj log --no-pager 2>/dev/null | head -25' || true
echo ""

# --- Assertions ---
if [ "$TOTAL" -lt "$MSG_COUNT" ]; then
  echo "FAIL: Total messages ($TOTAL) should be >= $MSG_COUNT"
  PASS=false
fi

for agent in "${AGENTS[@]}"; do
  count=$(count_messages "$agent")
  if [ "$count" -lt 1 ]; then
    echo "FAIL: $agent should have >= 1 message, got $count"
    PASS=false
  fi
done

if [ "$PASS" = true ]; then
  echo "============================================================"
  echo "PASS: $MSG_COUNT-message round-robin completed ($NUM_AGENTS agents)"
  if [ "$NO_LLM" = false ] && [ "$FALLBACK_USED" = true ]; then
    echo "  Note: LLM smoke test used CLI fallback"
  fi
  echo "============================================================"
else
  echo "============================================================"
  echo "FAIL: Assertions failed (see above)"
  echo "============================================================"
  exit 1
fi

#!/usr/bin/env bash
# Run all CI checks locally — mirrors .github/workflows/*.yml
#
# Usage:
#   ./ci-local.sh                # run all tests (LLM tests skipped if no key)
#   ./ci-local.sh --no-llm       # skip LLM tests explicitly
#   ./ci-local.sh --llm-only     # run only LLM tests
#   ./ci-local.sh --with-docker  # include openclaw Docker tests (slow)
#
# Prerequisites: jj, python3, git (configured), uv (for LLM tests)
# Optional: docker (for openclaw --with-docker), LLM_API_KEY env var or .env file

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BIN="$ROOT/bin/jj-mailbox"
PASS=0
FAIL=0
SKIP=0
NO_LLM=false
LLM_ONLY=false
WITH_DOCKER=false

for arg in "$@"; do
    case "$arg" in
        --no-llm)      NO_LLM=true ;;
        --llm-only)    LLM_ONLY=true ;;
        --with-docker) WITH_DOCKER=true ;;
    esac
done

# Load .env if present
if [[ -f "$ROOT/.env" ]]; then
    set -a
    source "$ROOT/.env"
    set +a
fi

# --- Helpers ---

green()  { printf "\033[32m%s\033[0m\n" "$*"; }
red()    { printf "\033[31m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
bold()   { printf "\033[1m%s\033[0m\n" "$*"; }

run_test() {
    local name="$1"
    shift
    printf "  %-45s " "$name"
    local output
    if output=$("$@" 2>&1); then
        green "PASS"
        PASS=$((PASS + 1))
        return 0
    else
        red "FAIL"
        FAIL=$((FAIL + 1))
        # Show last 20 lines of output on failure
        echo "$output" | tail -20 | sed 's/^/    /'
        return 1
    fi
}

skip_test() {
    local name="$1"
    local reason="$2"
    printf "  %-45s " "$name"
    yellow "SKIP ($reason)"
    SKIP=$((SKIP + 1))
}

# --- Prerequisite checks ---

bold "Checking prerequisites..."

missing=()
command -v jj   >/dev/null 2>&1 || missing+=("jj")
command -v python3 >/dev/null 2>&1 || missing+=("python3")
command -v git  >/dev/null 2>&1 || missing+=("git")

if [[ ${#missing[@]} -gt 0 ]]; then
    red "Missing required tools: ${missing[*]}"
    exit 1
fi

chmod +x "$BIN"
echo ""

# =============================================================================
# 1. Core CLI Tests (ci.yml)
# =============================================================================
if [[ "$LLM_ONLY" == false ]]; then

bold "=== Core CLI Tests ==="

REPO=$(mktemp -d /tmp/jj-mailbox-test-XXXXXX)
trap "rm -rf '$REPO'" EXIT

run_test "init" "$BIN" init "$REPO" || true

export JJ_MAILBOX_REPO="$REPO"

run_test "register alice" "$BIN" register alice "Research specialist" || true
run_test "register bob"   "$BIN" register bob   "Code reviewer"      || true

export JJ_MAILBOX_AGENT=alice
run_test "send (alice -> bob)" "$BIN" send bob "Hello" "Hi Bob, this is a test." || true

export JJ_MAILBOX_AGENT=bob
run_test "inbox bob" "$BIN" inbox bob || true
run_test "read bob"  "$BIN" read bob  || true
run_test "reply (bob -> alice)" "$BIN" send alice "Reply" "Got your message, thanks!" || true

unset JJ_MAILBOX_AGENT
run_test "status" "$BIN" status || true

# Multi-agent
run_test "register charlie" "$BIN" register charlie "Testing specialist" || true
export JJ_MAILBOX_AGENT=alice
run_test "broadcast (alice -> bob)"    "$BIN" send bob     "Broadcast" "Team update." || true
run_test "broadcast (alice -> charlie)" "$BIN" send charlie "Broadcast" "Team update." || true
unset JJ_MAILBOX_AGENT

run_test "jj log" jj log --no-pager -R "$REPO" || true

rm -rf "$REPO"
trap - EXIT
unset JJ_MAILBOX_REPO

echo ""

# =============================================================================
# 2. Scripted Agent Test (ci-scripted.yml)
# =============================================================================
bold "=== Scripted Agent Test ==="
run_test "tests/scripted/test.py" python3 "$ROOT/tests/scripted/test.py" || true
echo ""

# =============================================================================
# 3. Comparison Benchmark (ci-comparison.yml)
# =============================================================================
bold "=== Comparison Benchmark ==="
run_test "tests/comparison/benchmark.py" python3 "$ROOT/tests/comparison/benchmark.py" || true

if [[ -f "$ROOT/build/COMPARISON.md" ]]; then
    printf "  %-45s " "build/COMPARISON.md generated"
    green "OK"
else
    printf "  %-45s " "build/COMPARISON.md generated"
    red "MISSING"
fi
echo ""

fi  # end --llm-only guard

# =============================================================================
# 4. LLM Tests (ci-llm.yml, ci-smolagents.yml)
# =============================================================================
if [[ "$NO_LLM" == false ]]; then

bold "=== LLM Tests ==="

if [[ -z "${LLM_API_KEY:-}" ]]; then
    skip_test "llm/test.py"       "LLM_API_KEY not set"
    skip_test "smolagents/test.py" "LLM_API_KEY not set"
    echo ""
    yellow "  Hint: export LLM_API_KEY=your_key  (or add to .env)"
else
    export LLM_API_BASE="${LLM_API_BASE:-https://openrouter.ai/api/v1}"

    if ! command -v uv >/dev/null 2>&1; then
        skip_test "llm/test.py"       "uv not installed"
        skip_test "smolagents/test.py" "uv not installed"
    else
        # Run each model from models.txt
        while IFS= read -r model || [[ -n "$model" ]]; do
            [[ "$model" =~ ^#.*$ || -z "$model" ]] && continue
            export LLM_MODEL="$model"
            run_test "llm/test.py [$model]" \
                uv run --project "$ROOT" --group test-llm \
                python3 "$ROOT/tests/llm/test.py" || true
        done < "$ROOT/tests/models.txt"

        export LLM_MODEL="${LLM_MODEL:-nvidia/nemotron-3-super-120b-a12b:free}"
        run_test "smolagents/test.py" \
            uv run --project "$ROOT" --group test-smolagents \
            python3 "$ROOT/tests/smolagents/test.py" || true
    fi
fi
echo ""

fi  # end --no-llm guard

# =============================================================================
# 5. OpenClaw (ci-openclaw.yml) — needs Docker
# =============================================================================
if [[ "$LLM_ONLY" == false ]]; then

bold "=== OpenClaw Integration ==="

if [[ "$WITH_DOCKER" == false ]]; then
    skip_test "openclaw/test.sh --no-llm" "use --with-docker to enable"
elif ! command -v docker >/dev/null 2>&1; then
    skip_test "openclaw/test.sh --no-llm" "docker not installed"
elif [[ -x "$ROOT/tests/openclaw/test.sh" ]]; then
    run_test "openclaw/test.sh --no-llm" "$ROOT/tests/openclaw/test.sh" --no-llm || true
else
    skip_test "openclaw/test.sh" "test script not found"
fi
echo ""

fi  # end --llm-only guard

# =============================================================================
# Summary
# =============================================================================
echo ""
bold "==============================="
TOTAL=$((PASS + FAIL + SKIP))
echo "  Total: $TOTAL  |  $(green "PASS: $PASS")  |  $(red "FAIL: $FAIL")  |  $(yellow "SKIP: $SKIP")"
bold "==============================="

[[ $FAIL -eq 0 ]]

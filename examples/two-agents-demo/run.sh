#!/usr/bin/env bash
# Quick demo: two agents talking via jj-mailbox on a single machine
# No Docker needed — just jj and git
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BIN="${SCRIPT_DIR}/../../bin/jj-mailbox"
DEMO_DIR="/tmp/jj-mailbox-demo"

echo "📬 jj-mailbox quick demo"
echo "========================"
echo ""

# Clean up
rm -rf "${DEMO_DIR}"
mkdir -p "${DEMO_DIR}"

# Step 1: Initialize
echo "1️⃣  Initializing mailbox repo..."
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" ${BIN} init "${DEMO_DIR}/mailbox"
echo ""

# Step 2: Register agents
echo "2️⃣  Registering agents..."
cd "${DEMO_DIR}/mailbox"
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" ${BIN} register alice "Research specialist"
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" ${BIN} register bob "Code reviewer"
echo ""

# Step 3: Alice sends a message to Bob
echo "3️⃣  Alice sends a message to Bob..."
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=alice \
  ${BIN} send bob "Research complete" "I found 3 viable approaches for the caching layer. Option A uses Redis, Option B uses in-memory LRU, Option C uses jj-mailbox (meta!). Recommend Option B for simplicity."
echo ""

# Step 4: Check Bob's inbox
echo "4️⃣  Checking Bob's inbox..."
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=bob \
  ${BIN} inbox bob
echo ""

# Step 5: Bob reads the message
echo "5️⃣  Bob reads the message:"
echo "---"
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=bob \
  ${BIN} read bob | python3 -m json.tool 2>/dev/null || \
  JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=bob ${BIN} read bob
echo "---"
echo ""

# Step 6: Bob replies
echo "6️⃣  Bob replies to Alice..."
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=bob \
  ${BIN} send alice "Re: Research complete" "Agreed on Option B. I will start the implementation. Can you write a short design doc in shared/artifacts/?"
echo ""

# Step 7: Check Alice's inbox
echo "7️⃣  Checking Alice's inbox..."
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" JJ_MAILBOX_AGENT=alice \
  ${BIN} inbox alice
echo ""

# Step 8: Show status
echo "8️⃣  Agent status:"
JJ_MAILBOX_REPO="${DEMO_DIR}/mailbox" ${BIN} status

# Step 9: Show jj log
echo "9️⃣  jj operation history:"
cd "${DEMO_DIR}/mailbox"
jj log --no-pager 2>/dev/null || echo "(jj log not available in this environment)"
echo ""

# Step 10: Show file tree
echo "🔟 Mailbox file tree:"
find "${DEMO_DIR}/mailbox" -not -path '*/.jj/*' -not -path '*/.git/*' | head -40 | sed "s|${DEMO_DIR}/mailbox/||"
echo ""

echo "✅ Demo complete!"
echo ""
echo "The mailbox repo is at: ${DEMO_DIR}/mailbox"
echo "To add a git remote for cross-machine sync:"
echo "  cd ${DEMO_DIR}/mailbox"
echo "  jj git remote add origin <your-git-url>"
echo "  jj git push --all"

#!/usr/bin/env bash
# Minimal jj-mailbox example: send one message, read it
set -euo pipefail

BIN="$(cd "$(dirname "$0")/../../bin" && pwd)/jj-mailbox"
DIR="/tmp/jj-mailbox-hello"
rm -rf "$DIR"

# Initialize and register two agents
"$BIN" init "$DIR"
cd "$DIR"
JJ_MAILBOX_REPO="$DIR" "$BIN" register alice "Researcher"
JJ_MAILBOX_REPO="$DIR" "$BIN" register bob "Reviewer"

# Alice sends a message to Bob
JJ_MAILBOX_REPO="$DIR" JJ_MAILBOX_AGENT=alice \
  "$BIN" send bob "Hello" "Hi Bob, let's collaborate!"

# Bob reads it
echo "--- Bob's inbox ---"
JJ_MAILBOX_REPO="$DIR" JJ_MAILBOX_AGENT=bob "$BIN" inbox bob
echo "--- Message content ---"
JJ_MAILBOX_REPO="$DIR" JJ_MAILBOX_AGENT=bob "$BIN" read bob

echo ""
echo "Done! Mailbox repo at: $DIR"

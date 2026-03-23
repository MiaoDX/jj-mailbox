#!/usr/bin/env bash
# jj-mailbox OpenClaw skill — thin wrapper around bin/jj-mailbox
# Keeps a single source of truth; the skill simply delegates.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${SCRIPT_DIR}/../../bin/jj-mailbox"

if [[ ! -x "${BIN}" ]]; then
  echo "Error: bin/jj-mailbox not found at ${BIN}" >&2
  echo "Ensure the jj-mailbox repo is intact." >&2
  exit 1
fi

exec "${BIN}" "$@"

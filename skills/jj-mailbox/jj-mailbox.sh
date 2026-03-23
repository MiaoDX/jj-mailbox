#!/usr/bin/env bash
# jj-mailbox skill wrapper — delegates to the canonical bin/jj-mailbox CLI.
# This file exists so the OpenClaw skill bundle includes an executable entry point.
# All logic lives in bin/jj-mailbox (single source of truth).

set -euo pipefail

# Resolve the real bin/jj-mailbox relative to this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="${SCRIPT_DIR}/../../bin/jj-mailbox"

if [[ ! -x "${BIN}" ]]; then
  echo "[jj-mailbox] Error: bin/jj-mailbox not found at ${BIN}" >&2
  echo "[jj-mailbox] Ensure the jj-mailbox repo is intact." >&2
  exit 1
fi

exec "${BIN}" "$@"

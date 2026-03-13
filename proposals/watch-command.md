# Proposal: `jj-mailbox watch` — Real-time Local Notification

> Extends jj-mailbox with filesystem-level inbox watching.
> jj-mailbox remains the source of truth.

## Problem

The sync daemon polls every 30 seconds (`jj git fetch` → check inbox → `jj git push`).
After a fetch brings in new messages, the agent has no way to know immediately —
it has to wait until its next polling cycle to discover them.

## Solution

Add a `watch` subcommand that uses OS-level filesystem events to notify agents
the instant a new message file appears in their inbox.

```bash
jj-mailbox watch --agent alice --exec "jj-mailbox read"
```

## Design

### How it works with the existing sync daemon

The two run **side by side** with separate responsibilities:

| Component | Responsibility | Frequency |
|-----------|---------------|-----------|
| `jj-mailbox sync` | fetch/push, sync with remote | 30s (configurable) |
| `jj-mailbox watch` | detect local file changes, notify agent | Real-time (ms) |

Workflow:
1. sync daemon fetches from remote → new message files appear in local inbox
2. watch daemon detects file creation → immediately notifies agent
3. Agent calls `jj-mailbox read` to process message
4. Agent calls `jj-mailbox send` to reply
5. sync daemon pushes on next cycle

**Result**: End-to-end latency drops from **up to 30s** to **sync interval + milliseconds**.

### Implementation

Uses **inotifywait** (Linux) or **fswatch** (macOS), with a fast-polling fallback:

```bash
cmd_watch() {
    local agent="${JJ_MAILBOX_AGENT}"
    local inbox_dir="inbox/${agent}/new"
    local exec_cmd="${1:-}"

    if command -v inotifywait &>/dev/null; then
        inotifywait -m -e create "${inbox_dir}" |
        while read -r dir event file; do
            log_info "New message: ${file}"
            if [[ -n "${exec_cmd}" ]]; then
                eval "${exec_cmd}"
            fi
        done
    elif command -v fswatch &>/dev/null; then
        fswatch -0 "${inbox_dir}" |
        while IFS= read -r -d '' file; do
            log_info "New message: $(basename "${file}")"
            if [[ -n "${exec_cmd}" ]]; then
                eval "${exec_cmd}"
            fi
        done
    else
        # Fallback: fast polling (3s)
        log_warn "No inotifywait or fswatch found, falling back to 3s polling"
        local last_count=0
        while true; do
            local count
            count=$(find "${inbox_dir}" -name '*.json' 2>/dev/null | wc -l)
            if [[ "${count}" -gt "${last_count}" ]]; then
                log_info "${count} new message(s)"
                if [[ -n "${exec_cmd}" ]]; then
                    eval "${exec_cmd}"
                fi
            fi
            last_count="${count}"
            sleep 3
        done
    fi
}
```

### Optional: push-on-send

When watch detects a new outgoing message (agent just called `jj-mailbox send`),
it can optionally trigger an immediate `jj git push` instead of waiting for the
next sync cycle. This further reduces end-to-end latency.

## Scope

```
Changed:
  + bin/jj-mailbox   — add `watch` subcommand (~50 lines bash)

Unchanged:
  = spec/PROTOCOL.md
  = inbox/ directory structure
  = sync daemon
  = all existing commands
```

## Dependencies

- No new runtime dependencies (inotifywait/fswatch are typically pre-installed)
- No protocol changes

## Validation

- Existing two-agent demo: replace polling with watch, verify latency improvement
- Test on Linux (inotifywait) and macOS (fswatch)
- Test fallback polling when neither tool is available

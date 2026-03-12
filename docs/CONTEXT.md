# jj-mailbox Full Project Context

> This document records all discussions, research conclusions, and decisions from concept to initial implementation.
> Used to restore full context in Claude Code or other environments.

---

## Project Founder

- GitHub: MiaoDX (Dongxu Miao)
- Background: Perception engineer at Xiaomi Auto, previously at Horizon Robotics and DeepMotion.ai
- Expertise: Computer vision, SLAM, autonomous driving perception, embedded systems (C++/Python)
- Related repos: DataLayer (message passing & data serialization for embedded platforms), openclaw_tweaking
- Runs two OpenClaw instances on different servers via Docker
- Currently uses Slack for bot-to-bot @mention interaction, has a repo with conversation logs

## Core Problem

Multiple independent OpenClaw instances (different servers, Docker-deployed) need agent-to-agent interaction.
Existing approaches all have limitations:
- **Slack**: Works, but high latency, limited formatting, platform dependency
- **Lark/Discord/Telegram**: Bot-to-bot direct interaction is limited
- **A2A Protocol**: Good standardization direction, but no native OpenClaw integration yet
- **openclaw-a2a (n00n0i)**: Cross-gateway communication with a2a_send/discover/broadcast tools
- **Message queues (NATS/Kafka)**: Too heavy for individual users

## Core Insight

Several jj (Jujutsu) VCS features are naturally suited for an agent communication layer:
1. **Concurrent safety** — safe by design, even when synced via rsync/Dropbox without corruption
2. **First-class conflicts** — conflicts are recorded as structured data, don't block workflow
3. **Working copy as commit** — writing files is automatically recorded, no explicit add/commit needed
4. **Operation log** — all operations have history, natural audit log
5. **Git compatible** — use any Git remote for sync, zero additional infrastructure

## Competitive Analysis Conclusions

**No existing project uses jj for agent-to-agent communication/mailbox layer.**

| Project | What it does | Difference from ours |
|---------|-------------|---------------------|
| ruvnet/agentic-jujutsu | jj CLI wrapper + MCP tools | VCS operation wrapper, not a communication layer. 383 npm downloads, community calls it "AI slop" |
| kli (Kleisli.IO) | CRDT + Git event-sourced task orchestration | Leans toward task orchestration, not general messaging |
| Agent Mail | Git inbox/outbox + file locks | Uses raw git, lacks jj's conflict safety |
| Claude Code Agent Teams | JSON files + flock() | Validates file-based communication, but no version control, no cross-machine |
| AgentFS (Turso) | SQLite + FUSE | Isolated state management, not communication |
| openclaw-a2a (n00n0i) | HTTP bridge cross-gateway | HTTP-based, not filesystem |

## Design Decisions

### Project Name: jj-mailbox
- `jj-` prefix for jj community discoverability
- `mailbox` is a classic CS concept, needs no explanation
- One-line positioning: **"Maildir for AI agents — version-controlled message passing powered by jj"**

### Account Strategy
- Under personal account `MiaoDX`, no separate organization
- Consider transfer when there's a second core contributor or adoption by a larger ecosystem

### Scope Control
- **V1 only covers two-agent communication**
- File conventions designed for N agents from day one
- Single-machine/cross-machine compatible: protocol layer is universal, sync layer is pluggable
- Only OpenClaw skill for now, no Codex/Claude Code adapter (but README mentions theoretical compatibility)

### Technical Architecture
```
Communication protocol layer (file conventions)     ← Universal for single/cross-machine, core spec
   │
Sync layer (pluggable)
   ├── Cross-machine: jj git fetch/push (via Git remote)
   ├── Single-machine: jj workspace (shared repo)
   └── Single-machine minimal: direct shared filesystem
```

### File Conventions (PROTOCOL.md core)
```
mailbox-repo/
├── agents/{name}/profile.json    # agent identity
├── agents/{name}/status.json     # agent status
├── inbox/{name}/new/*.json       # unread messages
├── inbox/{name}/processed/       # read messages
└── shared/                       # shared workspace
    ├── tasks/
    ├── knowledge/
    └── artifacts/
```

Message filename format: `{ISO-timestamp}_{sender}_{message-id}.json`
Message JSON contains: version, id, timestamp, from, to, type, subject, body, refs, metadata

## Cold-Start Strategy

### Community Entry Points
| Channel | URL | Purpose |
|---------|-----|---------|
| jj Discord | discord.gg/dkmfj3aGQN (~2,970 members) | Seed users |
| jj GitHub Discussions | github.com/jj-vcs/jj/discussions "Show and Tell" | Exposure |
| awesome-jj | github.com/Necior/awesome-jj (139 stars) | List inclusion |
| OpenClaw ClawHub | clawhub.com (~13,700 skills) | Skill publishing |
| Awesome OpenClaw Skills | github.com/VoltAgent/awesome-openclaw-skills | List inclusion |
| Hacker News | Show HN | Cold-start traffic |

### Launch Path
1. Polish README to perfection (with terminal GIF, before/after comparison)
2. Post on jj Discord + Discussions
3. Hacker News Show HN
4. ClawHub publish
5. Full awesome list coverage
6. Technical blog post

### Narrative Angle
Natural evolution from "embedded IPC" to "agent IPC" — the DataLayer repo is the connecting point

### Demo Plan
1. **Slack before**: Existing two Claws conversing in Slack (have records)
2. **jj-mailbox after**: Same task completed with jj-mailbox
3. **Terminal GIF**: Split-screen comparison
4. **CI LLM demo**: Two agents using free OpenRouter models in GitHub Actions

## Completed File Checklist

| File | Lines | Status |
|------|-------|--------|
| `README.md` | ~100 | ✅ Done |
| `spec/PROTOCOL.md` | 192 | ✅ Done |
| `bin/jj-mailbox` | 402 | ✅ Done, passed end-to-end tests |
| `skills/jj-mailbox/SKILL.md` | 92 | ✅ Done |
| `examples/two-agents-demo/run.sh` | 84 | ✅ Done |
| `docker/docker-compose.yml` | 109 | ✅ Done |
| `docker/Dockerfile` | 33 | ✅ Done |
| `.github/workflows/ci.yml` | ~150 | ✅ Done (auto-runs on push, no API key needed) |
| `.github/workflows/demo-llm.yml` | ~243 | ✅ Done (manual trigger, supports Nemotron-free/custom) |
| `LICENSE` | MIT | ✅ |
| `.gitignore` | - | ✅ |

## CI Configuration Notes

### ci.yml (automatic, no configuration needed)
Auto-runs on every push, tests: init → register → send → inbox → read → bidirectional → status → multi-agent → jj history

### demo-llm.yml (manual trigger, requires secret)
Add `LLM_API_KEY` in repo Settings → Secrets → Actions

Two presets:
- `nemotron-free` (default): Nemotron 3 Super via OpenRouter, completely free
  - API base: https://openrouter.ai/api/v1
  - Model: nvidia/nemotron-3-super-120b-a12b:free
- `custom`: Any OpenAI-compatible API

## Key Reference Links

- jj official: https://github.com/jj-vcs/jj
- jj docs: https://docs.jj-vcs.dev/latest/
- awesome-jj: https://github.com/Necior/awesome-jj
- OpenClaw skills docs: https://docs.openclaw.ai/tools/skills
- ClawHub: https://docs.openclaw.ai/tools/clawhub
- Claude Code Agent Teams architecture: https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html
- Nemotron 3 Super (free): https://openrouter.ai/nvidia/nemotron-3-super-120b-a12b:free
- openclaw-a2a: https://github.com/n00n0i/openclaw-a2a
- Maildir pattern: https://en.wikipedia.org/wiki/Maildir

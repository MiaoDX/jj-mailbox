# Proposal: Platform Bridge — Slack/Feishu/Discord/Telegram Adapters

> Bridges external chat platforms into jj-mailbox.
> jj-mailbox remains the source of truth — the bridge is just a translator + courier.

## Problem

Users message `@agent` in Slack or Feishu, but agents only know how to read
jj-mailbox inboxes. Today this requires manual copy-paste. We need automatic
bridging from external platforms into jj-mailbox.

## Solution

A standalone bridge process that:
1. Connects to external platforms via their WebSocket/push APIs
2. Translates incoming messages into jj-mailbox format
3. Writes them to agent inboxes using `jj-mailbox send`
4. Watches for agent replies and forwards them back to the platform

```
                ┌──────────────────────────────────────┐
                │         External Platforms             │
                │  Slack   Feishu   Discord   Telegram   │
                └──┬───────┬───────┬────────┬──────────┘
                   │       │       │        │
                ┌──▼───────▼───────▼────────▼──────────┐
                │        Platform Bridge (new)           │
                │  ┌────────┐ ┌────────┐ ┌──────────┐  │
                │  │ Slack  │ │ Feishu │ │   ...    │  │
                │  │Adapter │ │Adapter │ │ Adapter  │  │
                │  └───┬────┘ └───┬────┘ └────┬─────┘  │
                │      └──────────┼───────────┘        │
                │         Unified format                │
                └──────────────┬───────────────────────┘
                               │ jj-mailbox send/read
                ┌──────────────▼───────────────────────┐
                │    jj-mailbox (unchanged, source of truth) │
                │                                       │
                │  inbox/alice/new/*.json                │
                │  inbox/bob/new/*.json                  │
                │  shared/tasks/*.json                   │
                └──────────────────────────────────────┘
```

**Key principle**: All messages pass through jj-mailbox's file protocol.
The bridge is an entry point and a courier, not a message bus.

## Architecture

### Inbound flow: Platform → Agent

```
Slack message "@gsd help me look up XXX"
      │
      ▼
  Slack Adapter (WebSocket / Socket Mode connection)
      │
      ▼  Translates to jj-mailbox send
      │
  jj-mailbox send gsd "[slack] #copycat — MiaoDX" "help me look up XXX" \
      --metadata '{"bridge":{"platform":"slack","channel":"#copycat",...}}'
      │
      ▼
  inbox/gsd/new/2026-03-13T10-00-00Z_slack-bridge_msg-xxx.json
```

### Outbound flow: Agent → Platform

The bridge agent `slack-bridge` is a **regular jj-mailbox agent** whose inbox
serves as the reply queue:

```
Agent reads message:
  metadata.bridge.platform = "slack"
  metadata.bridge.channel = "#copycat"
  metadata.bridge.thread_id = "1710300000.123456"

Agent replies:
  jj-mailbox send slack-bridge "Reply" "Here is my answer" \
    --metadata '{"reply_to":{"platform":"slack","channel":"#copycat","thread_id":"..."}}'

Bridge's reply watcher detects message in slack-bridge's inbox
  → Parses metadata.reply_to
  → Calls slack_adapter.send_reply(channel, thread_id, text)
```

This fully reuses jj-mailbox's message mechanism — no new outbox directory or protocol needed.

## Adapter Interface

```python
# bridge/adapter_base.py
class PlatformAdapter:
    """Base class for all platform adapters."""

    def connect(self) -> None:
        """Establish connection to platform (WebSocket/long-polling/etc.)."""
        raise NotImplementedError

    def on_message(self, callback: Callable[[BridgeMessage], None]) -> None:
        """Register incoming message callback."""
        raise NotImplementedError

    def send_reply(self, channel: str, thread_id: str, text: str) -> None:
        """Send a reply back to the platform."""
        raise NotImplementedError

    def disconnect(self) -> None:
        """Disconnect from platform."""
        raise NotImplementedError


@dataclass
class BridgeMessage:
    """Unified representation of a platform message for writing to jj-mailbox."""
    platform: str          # "slack" | "feishu" | "discord" | "telegram"
    channel: str           # Source channel/group
    sender_name: str       # Sender display name
    sender_id: str         # Platform-native user ID
    text: str              # Message body
    thread_id: str | None  # Platform-native thread ID (for threaded replies)
    timestamp: str         # Original send time (ISO 8601)
    mentions: list[str]    # @mentioned agent names
    raw: dict              # Raw platform message (for debugging)
```

## Slack Adapter Example

```python
# bridge/adapters/slack.py
class SlackAdapter(PlatformAdapter):
    def __init__(self, app_token: str, bot_token: str):
        self.app = AsyncApp(token=bot_token)
        self.socket = AsyncSocketModeHandler(self.app, app_token)

    async def connect(self):
        # Slack Socket Mode — no public URL required
        @self.app.event("message")
        async def handle_message(event, say):
            msg = BridgeMessage(
                platform="slack",
                channel=event["channel"],
                sender_name=await self._resolve_username(event["user"]),
                sender_id=event["user"],
                text=event["text"],
                thread_id=event.get("thread_ts"),
                timestamp=event["ts"],
                mentions=self._extract_mentions(event["text"]),
                raw=event,
            )
            if self._callback:
                self._callback(msg)

        await self.socket.start_async()
```

## Bridge Main Process

```python
# bridge/main.py
class PlatformBridge:
    """Main bridge process: receives platform messages into jj-mailbox,
    forwards agent replies back to platforms."""

    def __init__(self, mailbox_repo: str, config: BridgeConfig):
        self.mailbox_repo = mailbox_repo
        self.config = config
        self.adapters: dict[str, PlatformAdapter] = {}

    def start(self):
        # 1. Start platform adapters
        for platform, adapter_config in self.config.platforms.items():
            adapter = create_adapter(platform, adapter_config)
            adapter.on_message(self._on_platform_message)
            adapter.connect()
            self.adapters[platform] = adapter

        # 2. Start reply watcher (reads agent replies, sends back to platform)
        self._start_reply_watcher()

    def _on_platform_message(self, msg: BridgeMessage):
        """Platform message received → write to jj-mailbox."""
        recipients = msg.mentions or [self.config.default_agent]

        for recipient in recipients:
            subprocess.run([
                "jj-mailbox", "send", recipient,
                f"[{msg.platform}] {msg.channel} — {msg.sender_name}",
                msg.text,
                "--metadata", json.dumps({
                    "bridge": {
                        "platform": msg.platform,
                        "channel": msg.channel,
                        "sender_id": msg.sender_id,
                        "thread_id": msg.thread_id,
                    }
                })
            ], cwd=self.mailbox_repo)
```

## Message Format Extension

Extends jj-mailbox's existing JSON schema via **metadata only** (fully backward compatible):

```json
{
  "version": "0.1",
  "id": "msg-abc123",
  "timestamp": "2026-03-13T10:00:00Z",
  "from": "slack-bridge",
  "to": "gsd",
  "type": "message",
  "subject": "[slack] #copycat — MiaoDX",
  "body": "Help me look up this API usage",
  "refs": [],
  "metadata": {
    "bridge": {
      "platform": "slack",
      "channel": "#copycat",
      "channel_id": "C0AJN5URP7A",
      "sender": {
        "name": "MiaoDX",
        "platform_id": "U0AJN5URP7A"
      },
      "thread_id": "1710300000.123456",
      "original_timestamp": "2026-03-13T09:59:58Z"
    }
  }
}
```

Agents that don't care about the source platform just read `body` as usual.
Agents that do can inspect `metadata.bridge`.

## Identity Mapping

A simple config file, version-controlled in the mailbox repo:

```json
// config/identity-map.json
{
  "mappings": [
    {
      "mailbox_agent": "miaodx",
      "platforms": {
        "slack": { "user_id": "U0AJN5URP7A", "display_name": "MiaoDX" },
        "feishu": { "user_id": "ou_xxx", "display_name": "Dongxu Miao" }
      }
    }
  ],
  "agent_routing": {
    "gsd": {
      "responds_to_channels": ["#copycat", "#dev"],
      "responds_to_mentions": true
    },
    "wlb": {
      "responds_to_channels": ["#general"],
      "responds_to_mentions": true
    }
  }
}
```

## Bridge Configuration

```yaml
# config/bridge.yaml
mailbox_repo: /path/to/jj-mailbox-repo
default_agent: gsd  # When no @mention, route to this agent

platforms:
  slack:
    enabled: true
    app_token: ${SLACK_APP_TOKEN}      # Environment variable reference
    bot_token: ${SLACK_BOT_TOKEN}
    channels:
      - "#copycat"
      - "#dev"

  feishu:
    enabled: false
    app_id: ${FEISHU_APP_ID}
    app_secret: ${FEISHU_APP_SECRET}

  discord:
    enabled: false
    bot_token: ${DISCORD_BOT_TOKEN}
```

## Platform Notes

| Platform | WebSocket API | Auth | Notes |
|----------|---------------|------|-------|
| **Slack** | Socket Mode | Bot token + app token | Events API over WebSocket |
| **Feishu** | WebSocket connection | App ID + App Secret | Real-time events |
| **Discord** | Gateway | Bot token | Intents-based events |
| **Telegram** | Webhook or long-polling | Bot token | Webhook preferred for push |

## Scope

```
Changed:
  + bridge/                  — Platform bridge process (standalone Python package)
  +   adapter_base.py        — Adapter base class
  +   adapters/slack.py      — Slack Socket Mode adapter
  +   adapters/feishu.py     — Feishu adapter (Phase 2)
  +   main.py                — Bridge main process
  +   config.py              — Config loader
  + config/bridge.yaml       — Bridge configuration
  + config/identity-map.json — Cross-platform identity mapping

Unchanged:
  = spec/PROTOCOL.md          — Message format unchanged (metadata-only extension)
  = bin/jj-mailbox            — Existing commands unchanged
  = inbox/ directory structure — Unchanged
  = sync daemon               — Unchanged
```

## Implementation Phases

### Phase 1: Slack Bridge

- Slack Socket Mode adapter
- Bridge main process with reply watcher
- End-to-end: Slack message → jj-mailbox inbox → agent processes → reply in Slack thread

### Phase 2: Feishu Bridge + Identity Mapping

- Feishu adapter
- `config/identity-map.json`
- Cross-platform: same user's Slack and Feishu messages linked

### Phase 3: Polish

- Discord / Telegram adapters (on demand)
- Health checks and reconnection
- Message deduplication (don't duplicate from multiple platforms)
- Monitoring and alerting

## Comparison with GSD/WLB Unified WebSocket Gateway Proposal

| Aspect | GSD/WLB Proposal | This Proposal |
|--------|-----------------|---------------|
| **Positioning** | Standalone WebSocket Gateway | jj-mailbox extension layer |
| **Message storage** | Gateway manages its own queue | All written to jj-mailbox (files + jj version control) |
| **Offline handling** | Custom per-agent queue (TTL 24h) | Not needed — jj-mailbox inbox is a persistent queue |
| **Agent interface** | New `gateway.subscribe()` API | Unchanged — still `jj-mailbox read/send` |
| **Audit trail** | Not addressed | Automatic — jj operation log |
| **Conflict safety** | Not addressed | Automatic — jj concurrent write safety |
| **Complexity** | High (new message middleware from scratch) | Low (one bridge process + existing CLI) |

**Key difference**: This proposal does not create a new message protocol. All messages
use jj-mailbox's existing file format. The Platform Bridge is just a translator and
courier — it moves external platform messages into jj-mailbox, and moves jj-mailbox
replies back to platforms.

## Validation

1. Send `@gsd hello` in Slack → message appears in gsd's inbox
2. gsd replies → reply appears in the original Slack thread
3. All messages have full records in jj-mailbox with version history

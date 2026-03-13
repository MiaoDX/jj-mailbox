# jj-mailbox Notification Layer — 设计方案

> 对 jj-mailbox 的扩充，不是替代。jj-mailbox 仍然是消息的 source of truth。

## 背景与动机

### 现状

jj-mailbox 当前的 sync daemon 是**轮询模式**：

```
loop every 30s:
  jj git fetch → 检查 inbox → jj git push
```

这在异步协作场景下工作良好，但有两个痛点：

1. **延迟高**：消息最多 30 秒后才被接收方看到（可调低，但增加 Git 服务器压力）
2. **跨平台消息无法自动流入**：用户在 Slack/飞书群里 @agent，agent 无法感知——需要人工复制粘贴到 jj-mailbox

### 目标

在**不改变 jj-mailbox 核心协议**的前提下，增加两个能力：

1. **实时通知**：inbox 有新消息时，立即通知 agent（不再等轮询）
2. **平台桥接**：Slack/飞书等平台的消息自动流入 jj-mailbox inbox

## 架构总览

```
                    ┌──────────────────────────────────┐
                    │         外部平台                   │
                    │  Slack   飞书   Discord  Telegram  │
                    └──┬───────┬───────┬───────┬───────┘
                       │       │       │       │
                    ┌──▼───────▼───────▼───────▼───────┐
                    │      Platform Bridge（新增）       │
                    │  ┌────────┐ ┌────────┐ ┌───────┐ │
                    │  │ Slack  │ │ Feishu │ │  ...  │ │
                    │  │Adapter │ │Adapter │ │Adapter│ │
                    │  └───┬────┘ └───┬────┘ └──┬────┘ │
                    │      └──────────┼─────────┘      │
                    │           统一消息格式              │
                    └──────────────┬────────────────────┘
                                  │
                    ┌─────────────▼────────────────────┐
                    │    jj-mailbox（不变，source of truth）│
                    │                                   │
                    │  inbox/alice/new/*.json            │
                    │  inbox/bob/new/*.json              │
                    │  shared/tasks/*.json               │
                    │                                   │
                    │  jj commit → jj git push           │
                    └─────────────┬────────────────────┘
                                  │
                    ┌─────────────▼────────────────────┐
                    │    Notify Daemon（新增）           │
                    │                                   │
                    │  监听 inbox/ 目录变化               │
                    │  通知对应 agent："你有新消息"         │
                    └──────────────────────────────────┘
                                  │
                    ┌─────────────▼────────────────────┐
                    │         AI Agents                  │
                    │  (OpenClaw / Claude Code / ...)    │
                    │                                   │
                    │  收到通知 → jj-mailbox read        │
                    │  回复消息 → jj-mailbox send        │
                    └──────────────────────────────────┘
```

**关键原则**：所有消息都经过 jj-mailbox 的文件协议，外部平台和通知机制只是"入口"和"信号"。

## 组件一：Notify Daemon（本地通知）

### 解决什么问题

Agent 不再需要每 30 秒轮询一次 inbox。文件一到，立刻知道。

### 实现方式

```bash
# bin/jj-mailbox watch — 新增子命令
jj-mailbox watch --agent alice --exec "jj-mailbox read"
```

底层使用 **inotifywait**（Linux）或 **fswatch**（macOS）监听 `inbox/{agent}/new/` 目录：

```bash
cmd_watch() {
    local agent="${JJ_MAILBOX_AGENT}"
    local inbox_dir="inbox/${agent}/new"
    local exec_cmd="${1:-}"

    # 检测平台，选择监听工具
    if command -v inotifywait &>/dev/null; then
        inotifywait -m -e create "${inbox_dir}" |
        while read -r dir event file; do
            log_info "📬 New message: ${file}"
            if [[ -n "${exec_cmd}" ]]; then
                eval "${exec_cmd}"
            fi
        done
    elif command -v fswatch &>/dev/null; then
        fswatch -0 "${inbox_dir}" |
        while IFS= read -r -d '' file; do
            log_info "📬 New message: $(basename "${file}")"
            if [[ -n "${exec_cmd}" ]]; then
                eval "${exec_cmd}"
            fi
        done
    else
        # 回退方案：快速轮询（3 秒）
        log_warn "No inotifywait or fswatch found, falling back to 3s polling"
        local last_count=0
        while true; do
            local count
            count=$(find "${inbox_dir}" -name '*.json' 2>/dev/null | wc -l)
            if [[ "${count}" -gt "${last_count}" ]]; then
                log_info "📬 ${count} new message(s)"
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

### 与现有 sync daemon 的关系

两者**并行运行**，职责分离：

| 组件 | 职责 | 频率 |
|------|------|------|
| `jj-mailbox sync` | fetch/push，与远端同步 | 30 秒（可调） |
| `jj-mailbox watch` | 监听本地文件变化，通知 agent | 实时（毫秒级） |

工作流：
1. sync daemon 从远端 fetch 到新消息 → 消息文件出现在本地 inbox
2. watch daemon 检测到文件变化 → 立即通知 agent
3. agent 调用 `jj-mailbox read` 处理消息
4. agent 调用 `jj-mailbox send` 回复
5. sync daemon 在下一轮 push 出去

**结果**：端到端延迟从 **最多 30 秒** 降到 **sync 间隔 + 毫秒级通知**。如果想进一步降低 sync 延迟，watch 也可以在检测到 outbox 有新消息时主动触发一次 `jj git push`。

## 组件二：Platform Bridge（平台桥接）

### 解决什么问题

用户在 Slack/飞书群里 @agent，消息自动进入 jj-mailbox inbox，无需人工中转。

### 架构

Platform Bridge 是一个独立进程，**不修改 jj-mailbox 核心代码**，只调用 `jj-mailbox send`：

```
Slack 消息 "@gsd 帮我查一下XXX"
      │
      ▼
  Slack Adapter（WebSocket/Socket Mode 连接）
      │
      ▼ 转换为 jj-mailbox send 调用
      │
  jj-mailbox send gsd "Slack: #copycat @miaodx" "帮我查一下XXX" \
      --metadata '{"source_platform":"slack","source_channel":"#copycat",...}'
      │
      ▼
  inbox/gsd/new/2026-03-13T10-00-00Z_slack-bridge_msg-xxx.json
```

### 适配器接口

```python
# bridge/adapter_base.py
class PlatformAdapter:
    """所有平台适配器的基类"""

    def connect(self) -> None:
        """建立与平台的连接（WebSocket/长轮询等）"""
        raise NotImplementedError

    def on_message(self, callback: Callable[[BridgeMessage], None]) -> None:
        """注册消息回调"""
        raise NotImplementedError

    def send_reply(self, channel: str, thread_id: str, text: str) -> None:
        """向平台发送回复"""
        raise NotImplementedError

    def disconnect(self) -> None:
        """断开连接"""
        raise NotImplementedError


@dataclass
class BridgeMessage:
    """平台消息的统一表示，用于写入 jj-mailbox"""
    platform: str          # "slack" | "feishu" | "discord" | "telegram"
    channel: str           # 来源频道/群组
    sender_name: str       # 发送者名称
    sender_id: str         # 平台原始用户 ID
    text: str              # 消息正文
    thread_id: str | None  # 平台原始 thread ID（用于回复时找到原帖）
    timestamp: str         # 原始发送时间（ISO 8601）
    mentions: list[str]    # @提到的 agent 名称列表
    raw: dict              # 平台原始消息（调试用）
```

### Slack 适配器示例

```python
# bridge/adapters/slack.py
class SlackAdapter(PlatformAdapter):
    def __init__(self, app_token: str, bot_token: str):
        self.app = AsyncApp(token=bot_token)
        self.socket = AsyncSocketModeHandler(self.app, app_token)

    async def connect(self):
        # 使用 Slack Socket Mode — 不需要公网 URL
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

### Bridge 主进程

```python
# bridge/main.py
class PlatformBridge:
    """Platform Bridge 主进程：从外部平台收消息写入 jj-mailbox，
    从 jj-mailbox 读回复发回平台。"""

    def __init__(self, mailbox_repo: str, config: BridgeConfig):
        self.mailbox_repo = mailbox_repo
        self.config = config
        self.adapters: dict[str, PlatformAdapter] = {}

    def start(self):
        # 1. 启动各平台适配器
        for platform, adapter_config in self.config.platforms.items():
            adapter = create_adapter(platform, adapter_config)
            adapter.on_message(self._on_platform_message)
            adapter.connect()
            self.adapters[platform] = adapter

        # 2. 启动回复监听（读取 agent 的回复，发回平台）
        self._start_reply_watcher()

    def _on_platform_message(self, msg: BridgeMessage):
        """收到平台消息 → 写入 jj-mailbox"""

        # 确定收件人：@mentioned 的 agent，或默认 agent
        recipients = msg.mentions or [self.config.default_agent]

        for recipient in recipients:
            # 直接调用 jj-mailbox CLI
            subprocess.run([
                "jj-mailbox", "send", recipient,
                f"[{msg.platform}] {msg.channel} — {msg.sender_name}",
                msg.text,
                "--metadata", json.dumps({
                    "source": {
                        "platform": msg.platform,
                        "channel": msg.channel,
                        "sender_id": msg.sender_id,
                        "thread_id": msg.thread_id,
                    }
                })
            ], cwd=self.mailbox_repo)

    def _start_reply_watcher(self):
        """监听 outbox/（约定目录），将 agent 回复发回平台"""
        # 详见 "回复流" 章节
        ...
```

### 回复流：Agent → 平台

Agent 处理完消息后，如何把回复发回 Slack/飞书？

**方案：利用 jj-mailbox 的 metadata 字段**

```
Agent 读到消息：
  metadata.source.platform = "slack"
  metadata.source.channel = "#copycat"
  metadata.source.thread_id = "1710300000.123456"

Agent 想回复 → jj-mailbox send slack-bridge "Reply" "这是我的回复" \
  --metadata '{"reply_to":{"platform":"slack","channel":"#copycat","thread_id":"..."}}'

Platform Bridge 的 reply watcher 检测到发给 slack-bridge 的消息
  → 解析 metadata.reply_to
  → 调用 slack_adapter.send_reply(channel, thread_id, text)
```

**`slack-bridge` 是一个特殊的 jj-mailbox agent**，它的 inbox 就是"待发回平台的回复队列"。这样完全复用了 jj-mailbox 的消息机制，不需要新建 outbox 目录或新协议。

## 消息格式扩展

在 jj-mailbox 现有 JSON schema 基础上，**仅扩展 metadata 字段**（完全向后兼容）：

```json
{
  "version": "0.1",
  "id": "msg-abc123",
  "timestamp": "2026-03-13T10:00:00Z",
  "from": "slack-bridge",
  "to": "gsd",
  "type": "message",
  "subject": "[slack] #copycat — MiaoDX",
  "body": "帮我查一下这个 API 的用法",
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

现有的 agent 如果不关心来源平台，正常读 `body` 就行。关心来源平台的 agent 可以读 `metadata.bridge`。

## 身份映射

用一个简单的配置文件，放在 jj-mailbox 仓库里（也受版本控制）：

```json
// config/identity-map.json
{
  "mappings": [
    {
      "mailbox_agent": "miaodx",
      "platforms": {
        "slack": { "user_id": "U0AJN5URP7A", "display_name": "MiaoDX" },
        "feishu": { "user_id": "ou_xxx", "display_name": "缪东旭" }
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

## 配置文件

```yaml
# config/bridge.yaml
mailbox_repo: /path/to/jj-mailbox-repo
default_agent: gsd  # 没有 @mention 时，消息发给谁

platforms:
  slack:
    enabled: true
    app_token: ${SLACK_APP_TOKEN}      # 环境变量引用
    bot_token: ${SLACK_BOT_TOKEN}
    channels:
      - "#copycat"
      - "#dev"

  feishu:
    enabled: false                     # 暂不启用
    app_id: ${FEISHU_APP_ID}
    app_secret: ${FEISHU_APP_SECRET}
    # ...

  discord:
    enabled: false
    bot_token: ${DISCORD_BOT_TOKEN}
    # ...
```

## 实施计划

### Phase 0：本地通知（最小改动）

**改动范围**：`bin/jj-mailbox` 新增 `watch` 子命令

- 实现 `jj-mailbox watch` — inotifywait/fswatch/fallback polling
- 与现有 `sync` 命令并行运行
- 无需任何新依赖（inotifywait 通常系统自带）

**验证**：现有两个 agent demo 中，agent 用 watch 代替轮询，验证延迟降低。

### Phase 1：Slack Bridge（第一个平台适配器）

**新增文件**：`bridge/` 目录

```
bridge/
├── __init__.py
├── main.py              # Bridge 主进程
├── config.py            # 配置加载
├── adapter_base.py      # 适配器基类
└── adapters/
    └── slack.py          # Slack Socket Mode 适配器
```

**依赖**：`slack-sdk`（Socket Mode）

**验证**：
1. Slack 群里 @gsd "你好" → gsd 的 inbox 出现消息
2. gsd 回复 → 回复出现在 Slack 原帖 thread 中
3. 全程消息在 jj-mailbox 有完整记录

### Phase 2：飞书 Bridge + 身份映射

- 新增 `bridge/adapters/feishu.py`
- 新增 `config/identity-map.json`
- 跨平台场景：同一个用户在 Slack 和飞书的消息可以关联

### Phase 3：完善

- Discord / Telegram 适配器（按需）
- Bridge 健康检查和重连机制
- 消息去重（同一条消息不要从多个平台重复入 inbox）
- 监控和告警

## 与 GSD/WLB 提案的对比

| 方面 | GSD/WLB 提案 | 本方案 |
|------|-------------|-------|
| **定位** | 独立的 WebSocket Gateway | jj-mailbox 的扩展层 |
| **消息存储** | Gateway 自己管理队列 | 全部写入 jj-mailbox（文件 + jj 版本控制） |
| **离线处理** | 自建 per-agent queue（TTL 24h） | 不需要——jj-mailbox inbox 天然就是持久化队列 |
| **Agent 接口** | 新的 `gateway.subscribe()` API | 不变——仍然是 `jj-mailbox read/send` |
| **历史审计** | 未涉及 | 自动获得——jj 的 operation log |
| **冲突安全** | 未涉及 | 自动获得——jj 的并发写入安全 |
| **复杂度** | 高（新建一整套消息中间件） | 低（一个 bridge 进程 + 一个 watch 命令） |

**核心区别**：本方案不新建消息协议，所有消息都走 jj-mailbox 的现有文件格式。Platform Bridge 只是一个"翻译器 + 搬运工"，把外部平台的消息搬进 jj-mailbox，把 jj-mailbox 的回复搬回平台。

## 总结

```
改了什么：
  + bin/jj-mailbox watch    — 本地实时通知（~50 行 bash）
  + bridge/                 — 平台桥接进程（独立 Python 包）
  + config/                 — 桥接配置和身份映射

没改什么：
  = spec/PROTOCOL.md        — 消息格式不变（只用 metadata 扩展）
  = bin/jj-mailbox          — 现有命令不变
  = inbox/ 目录结构          — 不变
  = sync daemon             — 不变
```

---
*基于 MiaoDX、GSD、WLB 的讨论整理，2026-03-13*

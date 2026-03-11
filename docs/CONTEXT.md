# jj-mailbox 项目完整上下文

> 本文档记录了项目从构思到初始实现的所有讨论、调研结论和决策。
> 用于在 Claude Code 或其他环境中恢复完整上下文。

---

## 项目发起人

- GitHub: MiaoDX (缪东旭)
- 背景：小米汽车感知工程师，之前在地平线机器人和 DeepMotion.ai
- 专业：计算机视觉、SLAM、自动驾驶感知、嵌入式系统（C++/Python）
- 相关 repo：DataLayer（嵌入式平台的消息传递与数据序列化）、openclaw_tweaking
- 有两个 OpenClaw 实例在不同服务器上跑，通过 Docker 部署
- 目前用 Slack 做 bot-to-bot 的 @mention 交互，已经有对话记录的 repo

## 核心问题

多个独立的 OpenClaw 实例（不同服务器、Docker 部署），需要 agent 之间互相交互。
现有方案都有局限：
- **Slack**：能跑，但延迟高、格式受限、平台依赖
- **飞书/Discord/Telegram**：bot-to-bot 直接交互受限
- **A2A Protocol**：标准化方向好，但还没有和 OpenClaw 的原生集成
- **openclaw-a2a (n00n0i)**：专门做跨 Gateway 通信，有 a2a_send/discover/broadcast tools
- **消息队列（NATS/Kafka）**：对个人用户太重

## 核心洞察

jj (Jujutsu) VCS 的几个特性天然适合做 agent 通信层：
1. **并发安全**：设计上安全，即使用 rsync/Dropbox 同步也不会损坏
2. **一等公民冲突**：冲突被记录为结构化数据，不阻塞工作流
3. **Working copy 即 commit**：写文件自动记录，不需要显式 add/commit
4. **Operation log**：所有操作有历史记录，天然审计日志
5. **Git 兼容**：用任何 Git remote 做同步，零额外基础设施

## 竞品分析结论

**没有任何现有项目用 jj 做 agent 间通信/邮箱层。**

| 项目 | 做的事 | 和我们的区别 |
|------|--------|------------|
| ruvnet/agentic-jujutsu | jj CLI 封装层 + MCP tools | 是 VCS 操作封装，不是通信层。383 npm 下载，社区评价 "AI slop" |
| kli (Kleisli.IO) | CRDT + Git 事件溯源任务编排 | 偏任务编排，不是通用消息传递 |
| Agent Mail | Git inbox/outbox + 文件锁 | 用原始 git，没有 jj 的冲突安全 |
| Claude Code Agent Teams | JSON 文件 + flock() | 验证了文件通信的可行性，但无版本控制、无跨机 |
| AgentFS (Turso) | SQLite + FUSE | 隔离状态管理，不是通信 |
| openclaw-a2a (n00n0i) | HTTP Bridge 跨 Gateway | 基于 HTTP，不是文件系统 |

## 设计决策

### 项目名：jj-mailbox
- 带 `jj-` 前缀被 jj 社区搜到
- `mailbox` 是 CS 经典概念，不需要解释
- 一句话定位：**"Maildir for AI agents — version-controlled message passing powered by jj"**

### 账号策略
- 放在个人账号 `MiaoDX` 下，不单独建 organization
- 等有第二个核心贡献者或被更大生态 adopt 时再考虑 transfer

### Scope 控制
- **V1 只做两个 agent 之间的通信**
- 文件约定从一开始就设计成 N 个 agent 兼容
- 单机/跨机兼容：协议层通用，同步层可插拔
- 只做 OpenClaw skill，不做 Codex/Claude Code 适配（但 README 提到理论兼容）

### 技术架构
```
通信协议层（文件约定）     ← 单机/跨机通用，核心 spec
   │
同步层（可插拔）
   ├── 跨机：jj git fetch/push（通过 Git remote）
   ├── 单机：jj workspace（共享同一个 repo）
   └── 单机极简：直接共享文件系统
```

### 文件约定（PROTOCOL.md 的核心）
```
mailbox-repo/
├── agents/{name}/profile.json    # agent 身份
├── agents/{name}/status.json     # agent 状态
├── inbox/{name}/new/*.json       # 未读消息
├── inbox/{name}/processed/       # 已读消息
└── shared/                       # 共享工作区
    ├── tasks/
    ├── knowledge/
    └── artifacts/
```

消息文件名格式：`{ISO-timestamp}_{sender}_{message-id}.json`
消息 JSON 包含：version, id, timestamp, from, to, type, subject, body, refs, metadata

## 冷启动策略

### 社区入口
| 渠道 | 地址 | 用途 |
|------|------|------|
| jj Discord | discord.gg/dkmfj3aGQN (~2,970人) | 种子用户 |
| jj GitHub Discussions | github.com/jj-vcs/jj/discussions "Show and Tell" | 曝光 |
| awesome-jj | github.com/Necior/awesome-jj (139 stars) | 列表收录 |
| OpenClaw ClawHub | clawhub.com (~13,700 skills) | skill 发布 |
| Awesome OpenClaw Skills | github.com/VoltAgent/awesome-openclaw-skills | 列表收录 |
| Hacker News | Show HN | 冷启动流量 |

### 发布路径
1. README 做到极致（含 terminal GIF、before/after 对比）
2. jj Discord + Discussions 发帖
3. Hacker News Show HN
4. ClawHub publish
5. awesome 列表全覆盖
6. 技术博客

### 叙事角度
从"嵌入式 IPC"到"agent IPC"的自然演化——DataLayer repo 是连接点

### Demo 展示计划
1. **Slack before**：现有两个 Claw 在 Slack 里的对话（已有记录）
2. **jj-mailbox after**：同样任务用 jj-mailbox 完成
3. **Terminal GIF**：split-screen 对比
4. **CI LLM demo**：GitHub Actions 里两个 agent 用 MiMo/Kimi 对话

## 已完成的文件清单

| 文件 | 行数 | 状态 |
|------|------|------|
| `README.md` | 212 | ✅ 完成 |
| `spec/PROTOCOL.md` | 192 | ✅ 完成 |
| `bin/jj-mailbox` | 402 | ✅ 完成，通过端到端测试 |
| `skills/jj-mailbox/SKILL.md` | 92 | ✅ 完成 |
| `examples/two-agents-demo/run.sh` | 84 | ✅ 完成 |
| `docker/docker-compose.yml` | 109 | ✅ 完成 |
| `docker/Dockerfile` | 33 | ✅ 完成（jj 版本号需确认最新） |
| `.github/workflows/ci.yml` | ~100 | ✅ 完成（每次 push 自动跑，无需 API key） |
| `.github/workflows/demo-llm.yml` | ~130 | ✅ 完成（手动触发，支持 MiMo-free/Kimi/custom） |
| `LICENSE` | MIT | ✅ |
| `.gitignore` | - | ✅ |

## CI 配置说明

### ci.yml（自动，无需配置）
每次 push 自动跑，测试：init → register → send → inbox → read → bidirectional → status → multi-agent → jj history

### demo-llm.yml（手动触发，需要 secret）
需要在 repo Settings → Secrets → Actions 添加 `LLM_API_KEY`

三个预设：
- `mimo-free`（默认）：MiMo-V2-Flash via OpenRouter，完全免费
  - API base: https://openrouter.ai/api/v1
  - Model: xiaomi/mimo-v2-flash:free
- `kimi`：moonshot-v1-8k
  - API base: https://api.moonshot.cn/v1
- `custom`：任意 OpenAI 兼容 API

## 待办事项

- [ ] 确认 jj 最新版本号（Dockerfile 和 ci.yml 里写的是 v0.28.2）
- [ ] push 到 GitHub，确认 CI 绿色
- [ ] 在 GitHub Secrets 添加 LLM_API_KEY（OpenRouter key）
- [ ] 手动触发 LLM demo workflow，确认能跑
- [ ] 用现有两个 Claw 在 Slack 上录一次协作任务（before）
- [ ] 用 jj-mailbox 跑同样任务（after）
- [ ] 录 terminal GIF 做 README 对比
- [ ] 在 jj Discord/Discussions 发帖
- [ ] ClawHub publish
- [ ] 提交 awesome-jj PR
- [ ] Show HN

## 关键参考链接

- jj 官方：https://github.com/jj-vcs/jj
- jj 文档：https://docs.jj-vcs.dev/latest/
- awesome-jj：https://github.com/Necior/awesome-jj
- OpenClaw skills 文档：https://docs.openclaw.ai/tools/skills
- ClawHub：https://docs.openclaw.ai/tools/clawhub
- Claude Code Agent Teams 架构：https://nwyin.com/blogs/claude-code-agent-teams-reverse-engineered.html
- MiMo-V2-Flash (free)：https://openrouter.ai/xiaomi/mimo-v2-flash:free
- openclaw-a2a：https://github.com/n00n0i/openclaw-a2a
- Maildir 模式：https://en.wikipedia.org/wiki/Maildir

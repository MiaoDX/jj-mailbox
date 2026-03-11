# jj-mailbox 可行性与竞争全景分析

> **核心结论：用 jj 做 AI agent 文件级通信层，这个概念是真正的空白地带。没有现有项目在做完全一样的事。而且它恰好处于两个快速汇聚的趋势交叉点：jj 生态的增长（~25,700 GitHub stars，2025年9月举办了首届 JJ Con）和多 agent AI 系统的爆发——越来越多系统开始依赖文件系统做协调。**

---

## 一、文件级消息传递有深厚的历史根基

你的想法不是拍脑袋——"用文件系统做消息总线"这件事已经被证明可靠了几十年：

### Maildir 模式（最直接的前辈）

1995 年 Daniel J. Bernstein 设计的 Maildir 是经典范式：三个目录（`tmp/`、`new/`、`cur/`），通过原子 `rename()` 操作实现无锁、防崩溃、NFS 安全的消息投递。现在仍有多个生产库在用这个模式，包括 npm 上的 `@munogu/maildir-queue`、Perl 的 `IPC::DirQueue`（支持多主机场景）、Python 的 `fs-task-queue`（专为 HPC 集群设计——那些跑 Redis 或 RabbitMQ 太重的地方）。

### Plan 9 的哲学验证

Plan 9 的 9P 协议证明了"把所有服务暴露为文件"可以扩展到完全分布式系统。现代的 WSL 和 QEMU/VirtFS 都在用 9P 做跨边界文件共享。arXiv 上有篇 AWCP 论文（2602.20493）明确引用 Plan 9 作为设计灵感，用 Git 做传输层实现 agent 工作区委托。

### ⭐ Claude Code Agent Teams——最直接的验证

**这是最重要的发现**：Anthropic 在 2026 年 2 月发布的 Claude Code Agent Teams，其架构本质上就是你想做的 jj-mailbox 减去版本控制层——agent 之间通过读写 `~/.claude/teams/{team-name}/inboxes/` 目录下的 JSON 文件来通信，用 `flock()` 做互斥。整个多 agent 系统跑在磁盘上的 JSON 文件上——没有数据库，没有消息中间件。任务是单独的 JSON 文件，带依赖图（`blocks`/`blockedBy`），调试方法就是用 `watch -n 0.5 'tree ~/.claude/teams/'` 看文件树。

**这直接验证了你的核心架构假设：文件就是最好的 agent 通信协议。**

### 学术界也在汇聚

- **AgentGit**（arXiv:2511.00628）：给多 agent 工作流加上 Git 式的回滚和分支
- **Git-ContextController**：装备了 Git 上下文管理的 agent 在 SWE-Bench-Lite 上超越了 26 个领先系统（**48% vs 43%** 的解决率）
- **Legit**（2026年3月上线）：专门为 AI 原生应用设计的 Git 式版本控制 SDK

---

## 二、jj 生态正处于上升期，而且缺少你这个 use case

### 社区现状

- **~25,700 stars**，919 forks
- **Discord ~2,970 成员**（discord.gg/dkmfj3aGQN）
- 2025年9月举办了**首届 JJ Con**（话题包括元数据版本控制、Google 大规模使用、脚本接口）
- Steve Klabnik（据说离开 Oxide 去全职做 jj 生态）、Chris Krycho 等有影响力的人在推动
- 有一个 **awesome-jj 列表**（github.com/Necior/awesome-jj，139 stars）——你的项目可以提 PR 加入

### "jj + AI agent" 是正在形成的热点

多个独立作者不约而同地发现 jj 的特性适合 agent 工作流：
- Anthony Panozzo 记录了用 jj 防止 agent 工作丢失
- Slava Kurilyak 发了 "Use Jujutsu, Not Git" 专门面向 coding agent
- 多个 jj skills 出现在 Claude Code 和 OpenClaw 的 skill 注册表上

### jj-lib 的设计天然支持嵌入

`jj-lib` 是一个明确的可嵌入 Rust 库（crates.io/crates/jj-lib），官方架构文档说它"也适用于 GUI/TUI 或服务多用户请求的服务器"。存储层完全抽象，支持可插拔后端——Google 内部的 Piper/CitC 系统用的就是同样的架构。

### ruvnet 的 agentic-jujutsu 不构成真正威胁

- npm 只有 **383 次下载**
- 社区评价 "AI slop"
- "quantum-resistant" 是占位符实现
- 本质上只是 jj CLI 的封装，不是通信层

### 关键社区入口

| 渠道 | 地址 |
|------|------|
| Discord | discord.gg/dkmfj3aGQN（~2,970人） |
| GitHub Discussions | github.com/jj-vcs/jj/discussions（有 "Show and Tell" 分类） |
| IRC | #jujutsu on Libera Chat（和 Discord 互通） |
| awesome-jj | github.com/Necior/awesome-jj（项目发布后提 PR） |

---

## 三、OpenClaw Skill 生态非常适合分发

### Skill 架构

OpenClaw skill 本质上就是一个 `SKILL.md` 文件加 YAML 前言——不是编译代码，而是 LLM 在运行时读取并遵循的指令手册。可以声明二进制依赖（`jj`、`git`）和环境变量。

### ClawHub 注册表

- **~13,700 个社区 skills**
- 有语义搜索、semver 版本管理
- CLI 发布：`clawhub publish`
- 只需要一个 ≥1 周的 GitHub 账号
- 无正式审核流程，社区举报制（3 次举报自动隐藏）

### 什么样的 skill 最受欢迎

最高下载量的 skill 模式清晰——**扩展 agent 新能力的 skill 最受关注**：
- capability-evolver（35K+ 下载）
- wacli（16K+）
- self-improving-agent（15K+，132 stars——评分最高）

一个让 agent 之间通过新的 VCS 协议通信的 skill，完全符合这个模式。

### 另一个重要入口

**Awesome OpenClaw Skills**（github.com/VoltAgent/awesome-openclaw-skills）——870K 月浏览量，是官方文档之外的头号社区资源。

---

## 四、竞品全景——你的位置在哪里

**系统性调查的结论：没有任何现有项目用 jj 做 agent 间通信/邮箱层。**

| 项目 | 通信模型 | 冲突处理 | 历史/审计 | 成熟度 |
|------|---------|---------|----------|--------|
| **jj-mailbox**（你的方案） | jj 分支上的文件 | jj 一等公民冲突 | Operation log | 概念 |
| **kli**（Kleisli.IO） | Git 里的 JSONL 文件 | CRDT 合并 | 事件日志回放 | Pre-1.0 |
| **Agent Mail** | Git inbox/outbox | 文件锁 | Git 历史 | 活跃 |
| **Claude Code Teams** | 磁盘 JSON 文件 | flock() 互斥 | **无** | 生产 |
| **AgentFS**（Turso） | SQLite + FUSE/NFS | Copy-on-write | SQL 审计 | 活跃 |
| **Syncthing** | P2P 文件复制 | 冲突副本（不合并） | **无** | 成熟 |

### 你的三个独特优势

**没有任何竞品同时具备这三个：**

1. **Operation log**——完整的 agent 交互审计追踪。Claude Code Teams 完全没有这个
2. **一等公民冲突**——两个 agent 同时写同一个 mailbox，jj 保留两条消息而不是丢掉一条。flock() 方案做不到
3. **Git remote 兼容**——不同服务器的 agent 通过任意 Git 托管服务同步，零额外基础设施

### 需要注意的风险

有一篇详细分析了包管理器用 git 当数据库的失败案例（crates.io index、Homebrew、CocoaPods）——都在大量数据下出了问题。jj-mailbox 适合中小规模协调（**几十个 agent，几千条消息**），设计时要明确声明这个边界。

---

## 五、冷启动策略

### 数据支撑

- arXiv 一项研究发现，138 个 AI/LLM 工具在 Hacker News 曝光后，**平均 24 小时获得 121 stars**，一周内 289 stars
- 对 202 个开源开发者的调查显示，**#1 的弃用原因是安装太难**（34.7% 放弃）
- 有截图或 GIF 的 repo 比没有的多 **42% 的 stars**

### 推荐发布路径

**第一步：README 做到极致**

用 `vhs` 或 `terminalizer` 录一个分屏终端 GIF：左边是"没有 jj-mailbox"（手动文件轮询，消息丢失），右边是"有 jj-mailbox"（干净的版本化消息传递）。包含一行安装命令和 60 秒快速开始。

最有效的一句话定位：**"Maildir for AI agents — version-controlled message passing powered by jj"**——立即映射到一个已知模式（Maildir），同时传达新价值（版本控制 + agents）。

**第二步：种子在 jj 社区**

- 在 jj Discord 的 general 频道发帖
- 在 github.com/jj-vcs/jj/discussions 的 "Show and Tell" 开一个 discussion
- 定位：探索 jj 在传统 VCS 之外的潜力

**第三步：Hacker News "Show HN"**

用第一人称写：介绍自己 → 问题（agent 需要通信，消息队列太重）→ 洞察（jj 的特性为什么适合）→ 技术细节 → 邀请反馈。直接链到 GitHub repo。

**第四步：发布到 OpenClaw 生态**

1. `clawhub publish` 上 ClawHub
2. 提交到 github.com/openclaw/skills 官方 repo
3. 稳定后提交到 awesome-openclaw-skills

**第五步：awesome 列表全覆盖**

优先级：awesome-jj → awesome-mcp-servers（79K+ stars）→ awesome-ai-agents（多个列表）

**第六步：技术博客**

标题方向："为什么我用版本控制当 AI agent 的消息总线"——技术上有趣到可以上 HN，教育性足够让更广的社区看懂。发到 Dev.to、r/programming、r/LocalLLaMA。

---

## 六、你的 GitHub 画像与定位建议

github.com/MiaoDX 属于**缪东旭**，小米汽车感知工程师，此前在地平线机器人和 DeepMotion.ai 工作。专业背景是计算机视觉、SLAM、自动驾驶感知、嵌入式系统（C++/Python）。27 followers。

**最相关的连接点**：你有一个 **DataLayer 仓库**，描述是"analysis, thoughts, and suggestions on message passing and data marshalling for autonomous vehicles in and between embedded platforms"——这说明你在进程间通信和数据序列化方面有已有的思考。

**定位建议**：把 jj-mailbox 定位为从"嵌入式 IPC"到"agent IPC"的自然演化。你在自动驾驶领域的消息传递经验是一个有说服力的叙事弧线——"我在车载嵌入式系统里做过分布式消息传递，现在同样的问题出现在 AI agent 领域，而 jj 提供了一个更好的底层。"

---

## 七、最终战略建议

### 窗口期是真实但有时间限制的

jj 的增长、多 agent AI 的采用、Claude Code 文件级协调的验证——这三个趋势的汇聚创造了一个窄窗口，让 jj-mailbox 可以确立自己在这个领域的位置。

### 最高风险是 scope creep

概念简单优雅，就应该保持简单。最成功的小型 AI 工具有一个共同特点：**精确地解决一个问题**。jj-mailbox 应该是一个最小协议（往 inbox 目录写文件 → commit → push），让 jj 在底下处理所有分布式系统的难题。

**如果 README 需要超过 30 秒才能看懂，就已经失去了大部分潜在用户。**

### 具体行动项

1. ✅ 确认项目名和 repo
2. 🔨 写 PROTOCOL.md（文件约定 spec）
3. 🔨 写 sync daemon（100-200 行）
4. 🔨 写 OpenClaw SKILL.md
5. 🔨 搭 docker-compose demo（两个 agent 互相发消息）
6. 🎬 录 terminal GIF（before/after 对比）
7. 📣 发布到 jj Discord + Discussions
8. 📣 发布到 ClawHub
9. 📣 提交到 awesome-jj
10. 📣 Show HN

准备好了可以开始第 2-5 步。

# X Growth Agent · 产品方案（讨论底稿 v1）

> 状态：讨论中，未冻结。明天梳理完产品结构后据此开工。
> 优先级：**先做开源版**；托管 web 留给闭源付费版。

---

## 0. 一句话定义

用户给一批推特博主 → 后台引擎定时轮询 → 发现新帖就用**用户自己的 Claude Code / Codex** 生成「有意思的回复」候选 → 推到 **Telegram** → 用户挑一个自己去发。

核心理念：**Python 引擎是「一直醒着的调度员」，Claude Code / Codex 是「被叫醒思考一下就睡」的大脑。** 用户不需要一直开着聊天窗口。

---

## 1. 概念澄清（harness / agent loop / skill / MCP）

| 概念 | 是什么 |
|------|--------|
| **Harness** | 驱动 agent 跑起来的运行时（接收输入→调 LLM→执行工具→喂回结果）。Claude Code、Codex 本身就是 harness |
| **Agent loop** | Harness 内部的核心循环：模型输出→执行工具→返回→再输出，直到完成 |
| **Skill** | 一个带说明的“能力包”（SKILL.md + 脚本），注入给现有 harness，告诉模型遇到这类任务怎么做。不独立运行 |
| **MCP server** | 把外部能力（如 Twitter API）封装成标准工具，任何 harness 都能接 |

**对本项目的含义**：我们**不造 harness**（用户已有 Claude Code / Codex）。我们交付：Skill（怎么做）+ CLI/引擎（轮询、生成、通知）+ 可能的 MCP（封装 Twitter）。

---

## 2. 谁提供什么（密钥归属）

| 东西 | 谁提供 | 说明 |
|------|--------|------|
| Twitter 数据 | **用户自己** | 默认走 **RapidAPI**（如 twitter241，便宜、额度宽，`get-users-v2` 单次调用即可拉全 watchlist 最新帖）；也支持官方 X API v2 |
| LLM 能力 | **用户自己的 Claude Code / Codex** | 用他本机登录、模型、额度，我们不碰 LLM 成本。默认模型 **Opus 4.8** |
| Telegram Bot Token | 用户自己创建（1 分钟） | 付费版可托管 |
| 轮询引擎 + skill + 通知 | **我们（开源库）** | 核心交付物 |

**原则**：开源版 = 全 BYO（Bring Your Own Key），我们零运营成本。付费版才代管密钥。

> 运行流程图见 [`architecture.png`](architecture.png)（源文件 `architecture.mmd`）。

---

## 3. 整体架构

```
┌──────────────────────────────────────────────────────────┐
│  大脑层  用户本地 Claude Code / Codex（用户自己的额度）       │
│   skill①: 怎样生成“有意思的回复” + 范例库                    │
│   skill②: 导入关注列表 / 管理 watchlist                     │
│   手动:  “帮我看这条怎么回 / 加个博主 / 调风格”               │
└───────────────▲──────────────────────────────────────────┘
                │ 无头调起 claude -p  /  codex exec
┌───────────────┴──────────────────────────────────────────┐
│  引擎层  xgrowth（Python 常驻，后台一直醒着）                 │
│   轮询 watchlist 新帖（since_id 增量）→ 调大脑 → 出候选       │
│   engine 适配器:  claude | codex   （同时支持）             │
│   notifier 适配器: telegram | 飞书 | bark  （telegram 先行） │
└───────────────┬──────────────────────────────────────────┘
                │
          ┌─────▼─────┐  Telegram 卡片：原帖 + 2~3 条候选 + 按钮
          │  你的手机  │  [🔄换一批] [🔗原帖] [📋复制]
          └───────────┘  看顺眼 → 复制 → 自己去推特发
```

### 大脑层如何被驱动（关键）
Python 引擎用**无头模式**调起本地 coding agent：
- Claude Code：`subprocess` 调 `claude -p "..." --output-format json`，或用 `claude-agent-sdk`
- Codex：`codex exec`（非交互执行）
两者做成可切换适配器：`engine: claude | codex`。思考与人设全部走用户本地，模型/配置/额度都是他自己的。

---

## 4. 后台引擎跑在哪 —— 两方案

| | 方案 A：本地后台（开源版默认） | 方案 B：云端 7×24（付费版默认） |
|---|---|---|
| 形态 | `xgrowth start` 在用户电脑后台常驻 | 我们托管 / 用户一键部署到自己云 |
| 优点 | 零成本、隐私、立刻能用 | 关机不停、真 7×24、不占用户机器 |
| 缺点 | 电脑关机/休眠就停；机器得开着 | 有服务器成本；云端没有“本地 Claude Code” |
| 适合 | 个人玩家、开发者 | 付费用户 |

**方案 B 的大脑层难点**：云端没有用户本地 Claude Code。两种解法——
- B1：云端只轮询+通知，把帖子推回用户本地 Claude Code 思考（本地装轻客户端）
- B2：云端用 **Claude Agent SDK + 用户填的 Anthropic API Key** 思考（最简单，LLM 成本走用户 key）

**结论**：付费版倾向 **B2**（用户只填 Twitter + Anthropic 两个 key 即全自动）。**第一版先把 A 做扎实，B 留接口。**

---

## 5. 两条商业路线

### 🟢 开源路线（GitHub，获客 & 口碑）—— 优先做
- License：MIT（已建好）
- 交付：`pip install xgrowth` + 2 skill，全部 BYO key
- 价值：开发者 5 分钟跑起来；社区共建“神回复范例库”（护城河）
- 目标：SF / 海外开发者圈传播

### 🔵 闭源付费路线（网站，变现）—— 第二阶段
托管网站，让不会命令行的人也能用：注册 → 填/托管 key → 扫码连 Telegram → 导入关注勾选 → 选风格 → 开跑。

| 套餐 | 价格（示意） | 内容 |
|------|------|------|
| Free | $0 | 本地开源版，自给自足 |
| Pro | ~$19/月 | 云端 7×24、网站可视化、Telegram 托管、风格库进阶 |
| Team | ~$49/月 | 多账号、团队共享范例库、涨粉数据看板 |

**模式**：开源核心（引擎 + skill）+ 闭源外壳（网站/云调度/数据面板）。

---

## 6. 回复质量 —— 命根子是“有不有意思”

放弃沉重的双画像。用户人设是用户自己的事（他自己配置）。“有意思”做成 skill 里可迭代的资产：
- **多种回复策略**（不绑死）：梗回 / 神补刀 / 反直觉观点 / 一句戳中的提问 / 自嘲。每帖给 2~3 候选
- **反 AI 味硬规则**：禁“Great point!/Indeed/As an AI”；短；像真人随手打；允许玩梗、不完整句
- **few-shot 范例库**：质量真正来源，收集“真的很会回复的人”的神回复当样例，随用随长，社区共建

---

## 7. 用户画像 & 导入关注列表

- 人设交给用户自己配置，我们只降低门槛
- **导入关注列表**：Twitter API `GET /users/:id/following` 可分页拉全部关注
  - 注意：关注 ≠ 想监控。做成「一键拉全部 → 用户勾选要监控的子集 → 写进 watchlist」
  - 流程：`xgrowth import-following` → 列出（可按粉丝量/活跃度排序）→ 勾选 → 写 watchlist
  - 做成 skill，在 Claude Code 里对话式完成

---

## 8. Telegram（通知）

**Telegram = 国际版微信**，开发者机器人系统是全球通知事实标准。用户配置只需：
1. 手机装 Telegram，搜官方机器人 **@BotFather**
2. 发 `/newbot`，起名 → 拿到一串 **Token**
3. Token 填进 xgrowth 配置 → 完成

**卡片形态（带按钮）：**
```
🐦 @naval · 2 min ago
"The most important skill for the next decade is…"
─────────────
💬 候选① (神补刀)
"plot twist: it's knowing which AI to hand it to 🤝"
💬 候选② (反直觉)
"hot take: skills are depreciating assets now, taste isn't"
─────────────
[🔄 换一批]   [🔗 看原帖]   [📋 复制②]
```
- 🔄 换一批 → 引擎重新叫大脑生成不同风格
- 🔗 看原帖 → 跳转推特
- 📋 复制 → 放进剪贴板，切到推特粘贴发出

notifier 做成抽象层，telegram 先行，飞书 / Bark 插件式接入。

---

## 9. Web 端策略

| | 托管型 web（SaaS） | 本地 web 面板（localhost） |
|---|---|---|
| 形态 | 我们跑服务器，用户登录 | 引擎在本地顺手开 localhost:7777 |
| 谁掏钱 | 我们（违背开源零成本） | 用户自己机器，零成本 |
| 适合 | **闭源付费版** | **开源版可选加** |

**开源版做本地轻面板**（像 Syncthing / qBittorrent）：纯 Telegram 不便做“配置”和“回看历史”，本地面板补足。

```
┌─ xgrowth 本地面板 (localhost:7777) ────────┐
│ ● 引擎运行中   下次轮询 04:12               │
│ 监控列表 (12)        [导入关注] [+加博主]    │
│  @naval  @paulg  @levelsio …               │
│ 最近候选回复                                │
│  @naval 的帖 → 候选①②③  [复制] [换一批]      │
│ 风格设置: [神补刀] [反直觉] [自嘲] …         │
└────────────────────────────────────────────┘
```
技术轻：引擎已是 Python 常驻进程，挂个 FastAPI 顺手带出页面，不需服务器。

### 三层心智（最终定调）
| 层 | 用什么 | 干什么 |
|----|--------|--------|
| 手机 | Telegram | 收推送、挑回复、换风格 |
| 电脑·可视化 | 本地面板 localhost（开源版） | 管监控列表、回看历史、调风格 |
| 电脑·对话式 | Claude Code + skill | “帮我把这条回得再毒一点”“导入关注筛一下” |
| 网站（托管） | —— | 留给闭源付费版 |

---

## 10. 交付物清单（冻结后照此建仓库）

```
x-growth-agent/
├── engine/                 # Python 常驻引擎（开源）
│   ├── poller            # 轮询 + since_id 增量
│   ├── engines/          # claude.py / codex.py  ← 两个都做
│   ├── notifiers/        # telegram.py（先行）/ lark.py / bark.py
│   ├── panel/            # 本地轻面板 FastAPI（第二阶段）
│   └── cli.py            # xgrowth start / import-following / add ...
├── skills/                 # 注入用户 Claude Code 的能力包（开源）
│   ├── reply-craft/      # “有意思的回复” + 反AI味规则 + 范例库
│   └── watchlist/        # 导入关注、筛选、增删博主
├── examples/               # 神回复范例库（社区共建）
└── web/  (闭源，单独私有仓库)  # 付费网站 + 云调度 + 数据看板
```

---

## 11. 开源版分期

- **MVP（先做）**：CLI 引擎（claude + codex 适配器）+ reply-craft skill + watchlist skill + Telegram。先把「轮询→生成→推送」闭环跑通。**面板先不做。**
- **第二刀**：加本地轻面板（localhost），开源版可视化加分项。
- **托管 web**：闭源付费版再做。

---

## 12. 待拍板/待补充

1. 付费版云端大脑是否走 B2（用户填 Anthropic key，云端 SDK 思考）
2. `web/` 闭源部分：现在就单独建私有仓库，还是先放主仓库子目录
3. Twitter API 层级 / 监控博主规模（用户自行决定，影响成本与轮询策略）
4. 范例库初始来源（自己整理 vs 社区征集）

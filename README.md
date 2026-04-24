# Claude Feishu Gateway

把飞书消息转发到你本机的 AI Coding Agent，无需公网服务器。

通过飞书 WebSocket 长链接，只需在电脑上启动 `make gateway`，飞书 Bot 收到的消息就会转给本机运行时执行，再把结果发回飞书。

当前开源版支持 Claude、Codex、Gemini 三种 Gateway 运行时，并提供可选微信 listener。

![img](assets/basic-framework.png)

支持会话续聊、历史会话切换、执行中断、运行状态回传，以及可选的微信通道。

![img](assets/img_2026-03-09-01-51-40.png)

## 它能干什么

**1. 知识库结构 + 自我进化**

定义了数据怎么组织、知识怎么沉淀（基于PARA），让 agent 能快速查到需要的东西。知识库自检和自我进化是两个独立的定时任务，自动跑。

![](assets/self-evolve.png)

**2. 随时随地通过飞书驱动 agent**

手机打字或语音，消息经飞书转给本机 Claude / Codex / Gemini 运行时，执行完结果发回来。不用开电脑，不用 SSH，不用记命令。

![](assets/bot_usecase1.png)

**3. 多运行时 Gateway**

- `gateway_mode: claude`：沿用原有 Python Gateway
- `gateway_mode: codex`：启用 Node Gateway + Codex SDK
- `gateway_mode: gemini`：启用 Node Gateway + Gemini CLI Core
- 微信 listener 可作为可选通道接入同一套 Gateway

## 能力矩阵

| 能力 | Claude | Codex | Gemini | 微信 listener |
| --- | --- | --- | --- | --- |
| 飞书消息入口 | 是 | 是 | 是 | 可选旁路 |
| 会话续聊 | 是 | 是 | 是 | 走 Codex |
| `/sessions` 历史会话 | 是 | 是 | 是 | 不适用 |
| `/switch` 切换会话 | 是 | 是 | 是 | 不适用 |
| `/model` 模型切换 | 是 | 是 | 暂不支持 | 不适用 |
| `/stop` 中断任务 | 是 | 是 | 是 | 不适用 |

## 开源边界

这个仓库只保留通用 Gateway 能力：

- Claude / Codex / Gemini Gateway
- 飞书 Bot 长连接入口
- 可选微信 listener
- 会话、模型、停止等基础控制命令

明确不包含：

- 个人 skill passthrough
- 私有凭证 / 账号登录态
- 交易、金融、私有脚本链路
- 私人知识库或业务数据

## 包含什么

| 组件                     | 说明                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| **Gateway**        | Python Claude Gateway + Node Codex/Gemini Gateway |
| **Daemon**         | 类 cron 调度器，触发 Claude Code skill，支持自适应调度               |
| **CLAUDE.md**      | 知识库组织规则，Agent 行为准则                                       |
| **5 个通用 Skill** | knowledge-evolve, health-check, skill-creator, eat, root-review      |
| **feishu-push**    | 飞书 Webhook 推送工具（告警/日报/通用消息）                          |

## 快速开始

### 你需要准备

1. **一台普通电脑**（Windows / Mac / Linux）
2. **至少一种本机 Agent 登录态**
   - Claude：Claude Code，或兼容 Anthropic API 的第三方服务商
   - Codex：Codex CLI / Codex SDK 可用登录态
   - Gemini：Gemini CLI 登录态，或 `GEMINI_API_KEY`
3. **飞书自建应用**（免费，5 分钟创建）
4. **Node.js**
   - Codex / Gemini Gateway：Node.js `>=20`
   - 微信 listener：Node.js `>=22`

### 四步启动

```bash
# 1. 克隆仓库
git clone https://github.com/ketchupz1999/claude-feishu-gateway.git
cd claude-feishu-gateway

# 2. 安装依赖 + 配置飞书凭证
make init
cp .claude/secrets/feishu_app.example.json .claude/secrets/feishu_app.json
# 编辑 feishu_app.json，填入 app_id、app_secret、allowed_open_id

# 3. 选择 Gateway 运行时（默认 claude）
cp components/config.example.yaml components/config.yaml
# 编辑 components/config.yaml，把 gateway_mode 改成 claude / codex / gemini

# 4. 启动
make check      # 配置检查
make gateway    # 飞书网关
make daemon     # 后台守护（可选）
```

打开飞书，给你的 Bot 发一条消息，就开始干活了。

## Gateway 模式

### Claude 模式

默认模式，沿用原有 Python Gateway：

```bash
make gateway
```

前置条件：

- 已安装并登录 Claude Code，或已配置 `config/env.conf` 里的 Anthropic 兼容 API。

### Codex 模式

通过 `components/config.yaml` 启用：

```yaml
gateway_mode: codex
```

启动前安装并测试 Node Gateway：

```bash
make gateway-codex-install
make gateway-codex-build
make gateway-codex-test
make gateway
```

前置条件：

- 本机 Codex CLI / SDK 已可用。
- 不设置 `CODEX_API_KEY` 时，会复用本机 Codex 登录态。
- `CODEX_SANDBOX_MODE` 和 `CODEX_APPROVAL_POLICY` 可通过环境变量调整。

### Gemini 模式

通过 `components/config.yaml` 启用：

```yaml
gateway_mode: gemini
```

启动方式同 Node Gateway：

```bash
make gateway-codex-install
make gateway-codex-build
make gateway-codex-test
make gateway
```

前置条件：

- 本机 `gemini` CLI 已登录，或配置了 `GEMINI_API_KEY`。
- Gateway 不会在后台进程里弹浏览器登录；未登录时会直接向飞书返回“Gemini 未登录”。
- Gemini 模式当前不支持飞书侧 `/model` 切换，请在 Gemini CLI 配置里调整默认模型。

### 微信 listener

微信通道是可选能力：

```bash
make weixin-doctor
make weixin-setup
make weixin-login
```

要求 Node.js `>=22`，登录态默认写在本地 `data/weixin_state/`，不会进入 git。

如需随 Gateway 一起启动，启用 `components/config.yaml`：

```yaml
listener_channels:
  weixin:
    enabled: true
```

## 发布前验收

发版或提 PR 前建议至少跑：

```bash
make check
make gateway-codex-build
make gateway-codex-test
make weixin-doctor
```

本机联调建议按阶段验证：

1. `gateway_mode: codex`，飞书发送 `hi`、`/sessions`、`/stop`。
2. `gateway_mode: gemini`，飞书发送 `hi`、`/sessions`、一个只读文件问题。
3. 如果启用微信，先执行 `make weixin-login`，再启动 listener。

### 详细部署文档

第一次用或不熟悉命令行？看分步指南：

**macOS**

- [通过第三方服务商部署](docs/setup/mac-thirdparty.md)（StepFun / DeepSeek，无需订阅）
- [通过 Claude Code 订阅部署](docs/setup/mac-claude.md)
- [环境准备：安装 Python / Claude Code](docs/setup/prerequisites-mac.md)

**Windows**

- [通过第三方服务商部署](docs/setup/windows-thirdparty.md)（StepFun / DeepSeek，无需订阅）
- [环境准备：安装 Git / Python / Claude Code](docs/setup/prerequisites-windows.md)

## 第三方 API 配置

不想付 Claude 订阅？用兼容 Anthropic API 的第三方服务商也能跑。创建 `config/env.conf`：

```ini
ANTHROPIC_BASE_URL=https://api.stepfun.com/anthropic
ANTHROPIC_API_KEY=你的api_key
ANTHROPIC_MODEL=step-3.5-flash
```

`make gateway` 会自动加载这个文件。详见 [第三方 API 部署文档](docs/setup/mac-thirdparty.md#第四步配置第三方-api)。

## 自带 Skill

每个 Skill 就是一个 `SKILL.md` 文件，自然语言描述，不需要学框架 API：

| Skill                | 说明                           |
| -------------------- | ------------------------------ |
| `knowledge-evolve` | 知识库自检与进化，清理过时内容 |
| `health-check`     | 系统健康检查，一句话看全局状态 |
| `skill-creator`    | 让 agent 自己创建新 Skill      |
| `eat`              | 喂一篇文章，agent 消化进知识库 |
| `root-review`      | 根因分析，定位问题根源         |
| `feishu-push`      | 飞书 Webhook 推送              |

## 飞书聊天命令

| 命令             | 说明         |
| ---------------- | ------------ |
| `/model`       | 查看或切换模型（Claude / Codex 模式；Gemini 暂不支持） |
| `/clear`       | 清除当前会话 |
| `/new`         | 新建会话 |
| `/sessions`    | 查看会话列表 |
| `/switch 1`    | 按序号切换历史会话 |
| `/pin 1`       | 置顶历史会话（Codex 模式） |
| `/unpin 1`     | 取消置顶（Codex 模式） |
| `/stop`        | 中断当前执行 |

## 目录结构

```
claude-feishu-gateway/
├── components/
│   ├── servers/
│   │   ├── feishu_gateway.py        # Python Claude Gateway
│   │   ├── gateway_codex/           # Node Gateway（Codex / Gemini）
│   │   ├── weixin_listener/         # 微信 listener
│   │   ├── gateway_commands.py      # Python Gateway 命令路由
│   │   ├── gateway_messaging.py     # Python Gateway 消息解析与回复
│   │   └── gateway_sessions.py      # Python Gateway 会话管理
│   ├── daemon/
│   │   └── daemon.py                # 定时调度器
│   └── scripts/
│       ├── pipeline.sh              # Skill 执行器
│       └── claude_runner.py         # Claude CLI 封装（重试/熔断）
├── .claude/
│   ├── CLAUDE.md                    # Agent 行为准则 + 知识库规范
│   ├── skills/                      # Skill 定义（自然语言）
│   ├── rules/                       # 行为约束规则
│   └── agent-memory/                # Agent 独立记忆空间
├── memory/
│   ├── long/                        # 长期记忆（领域经验、认知积累）
│   └── scratch/                     # 临时记忆（定期沉淀到 long/）
├── knowledge/                       # PARA 体系知识库
├── todo/                            # 任务管理
├── config/                          # 配置文件（env.conf 等）
├── docs/setup/                      # 分步部署文档
├── scripts/                         # 运维脚本（preflight 等）
├── Makefile                         # 服务管理命令
└── requirements.txt
```

## License

MIT

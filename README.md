# Claude Feishu Gateway

无需公网、服务器

通过 WebSocket 长链接，只需在电脑启动(make gateway)，就可以跟飞书建立长链接🔗

当在飞书与 Bot 发消息时，飞书消息进来转给我们的电脑，电脑执行 Claude Code，结果回传飞书。

![img](assets/basic-framework.png)

支持 session 续聊、模型热切换

![img](assets/img_2026-03-09-01-51-40.png)

## 它能干什么

**1. 知识库结构 + 自我进化**

定义了数据怎么组织、知识怎么沉淀（基于PARA），让 agent 能快速查到需要的东西。知识库自检和自我进化是两个独立的定时任务，自动跑。

![](assets/self-evolve.png)

**2. 随时随地通过手机飞书驱动 agent**

手机打字或语音，消息经飞书转给 Claude Code，执行完结果发回来。不用开电脑，不用 SSH，不用记命令。

![](assets/bot_usecase1.png)

**3. Claude Code 的完整 Agent 能力**

Gateway 只做透传，不做裁剪。Claude Code 的所有能力——Skill、subagent、MCP、文件读写、命令执行——全部可用。

## 包含什么

| 组件                     | 说明                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| **Gateway**        | 200 行 Python，飞书消息转 Claude Code，支持 session 续聊、模型热切换 |
| **Daemon**         | 类 cron 调度器，触发 Claude Code skill，支持自适应调度               |
| **CLAUDE.md**      | 知识库组织规则，Agent 行为准则                                       |
| **5 个通用 Skill** | knowledge-evolve, health-check, skill-creator, eat, root-review      |
| **feishu-push**    | 飞书 Webhook 推送工具（告警/日报/通用消息）                          |

## 快速开始

### 你需要准备

1. **一台普通电脑**（Windows / Mac / Linux）
2. **模型服务**，二选一：
   - [Claude Code 订阅](https://claude.ai/claude-code)（推荐，能力最完整）
   - 兼容 Anthropic API 的第三方服务商（StepFun、DeepSeek 等），无需订阅
3. **飞书自建应用**（免费，5 分钟创建）

### 三步启动

```bash
# 1. 克隆仓库
git clone https://github.com/LieLieLiekey/claude-feishu-gateway.git
cd claude-feishu-gateway

# 2. 安装依赖 + 配置飞书凭证
make init
cp .claude/secrets/feishu_app.example.json .claude/secrets/feishu_app.json
# 编辑 feishu_app.json，填入 app_id、app_secret、allowed_open_id

# 3. 启动
make check      # 配置检查
make gateway    # 飞书网关
make daemon     # 后台守护（可选）
```

打开飞书，给你的 Bot 发一条消息，就开始干活了。

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
| `/clear`       | 清除当前会话 |
| `/new 名称`    | 新建命名会话 |
| `/sessions`    | 查看会话列表 |
| `/switch 名称` | 切换会话     |
| `/stop`        | 中断当前执行 |

## 目录结构

```
claude-feishu-gateway/
├── components/
│   ├── servers/
│   │   ├── feishu_gateway.py        # 飞书 WebSocket 网关（核心）
│   │   ├── gateway_commands.py      # 命令路由（/model, /clear, /stop ...）
│   │   ├── gateway_messaging.py     # 消息解析与回复
│   │   └── gateway_sessions.py      # 多会话管理与持久化
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

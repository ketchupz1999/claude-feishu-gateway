# macOS + 第三方 API（StepFun / DeepSeek 等）

没有 Claude Code 订阅也能用。只要服务商兼容 Anthropic API 协议，配一个文件就行

---

## 前置条件

- macOS 12+
- Python 3.10+ 和 Claude Code CLI 已安装 → 没装过？看 **[环境准备指南](prerequisites-mac.md)**
  > 不需要 Claude 订阅，只需要装好 CLI
  >
- 飞书账号
- 一个兼容 Anthropic API 的第三方服务商账号

### 目前已知兼容的服务商

| 服务商                                  | Base URL                               | 免费额度   | 备注     |
| --------------------------------------- | -------------------------------------- | ---------- | -------- |
| [StepFun](https://platform.stepfun.com/)   | `https://api.stepfun.com/anthropic`  | 注册送额度 | 国内直连 |
| [DeepSeek](https://platform.deepseek.com/) | `https://api.deepseek.com/anthropic` | 注册送额度 | 国内直连 |

> 只要支持 Anthropic Messages API 格式的服务商都可以，不限于以上两家

---

## 第一步：创建飞书自建应用

详细图文教程见 [飞书 Bot 创建指南](feishu-bot-setup.md)。和 Claude 订阅方案完全一样

---

## 第二步：获取第三方 API Key

API Key 是服务商给你的一串密钥，用来验证身份和计费。以 StepFun 为例：

1. 注册 [StepFun 开放平台](https://platform.stepfun.com/)
2. 进入 [API Keys 页面](https://platform.stepfun.com/interface-key) → 创建新 Key
3. 复制保存

DeepSeek 类似：注册 → 控制台 → 创建 API Key

---

## 第三步：下载代码 & 配置

打开终端（Spotlight 搜索 `终端` 或 `Terminal`），逐行粘贴执行：

```bash
# 克隆
git clone https://github.com/ketchupz1999/claude-feishu-gateway.git
cd claude-feishu-gateway

# 安装 Python 依赖包
pip3 install -r requirements.txt
```

然后创建飞书配置文件（把下面三个值替换成第一步中获取的真实值）：

```bash
mkdir -p .claude/secrets
cat > .claude/secrets/feishu_app.json << 'EOF'
{
  "app_id": "cli_你的app_id",
  "app_secret": "你的app_secret",
  "allowed_open_id": "ou_你的open_id"
}
EOF
```

> `allowed_open_id` 是安全限制——只有这个飞书用户的消息会被处理，其他人发的消息会被忽略。

---

## 第四步：配置第三方 API

这一步是关键——告诉 Gateway 使用第三方 API 而不是 Claude 官方服务。

### 方法一：写入配置文件（推荐）

复制一份示例配置：

```bash
cp config/env.conf.example config/env.conf
```

用文本编辑器打开 `config/env.conf`（可以用 `open config/env.conf` 或任意编辑器），填入你的配置：

```ini
# StepFun 示例（三行都要填）
ANTHROPIC_BASE_URL=https://api.stepfun.com/anthropic
ANTHROPIC_API_KEY=你的stepfun_api_key
ANTHROPIC_MODEL=step-3.5-flash

# DeepSeek 示例（和上面二选一，用哪个就去掉哪个的 # 号）
# ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
# ANTHROPIC_API_KEY=你的deepseek_api_key
# ANTHROPIC_MODEL=deepseek-chat
```

三个配置项的含义：

- `ANTHROPIC_BASE_URL` — 服务商的 API 地址
- `ANTHROPIC_API_KEY` — 第二步获取的 API Key
- `ANTHROPIC_MODEL` — 服务商的模型名（必须填，不能用 Claude 的模型名）

> 这个文件已在 `.gitignore` 中，不会被提交到 Git，你的 API Key 不会泄露。

保存后，`make check` 和 `make gateway` 都会自动读取，不需要额外操作。

### 方法二：手动设置环境变量

如果不想用配置文件，也可以在终端中手动设置（每次开新终端都要重新设）：

```bash
export ANTHROPIC_BASE_URL=https://api.stepfun.com/anthropic
export ANTHROPIC_API_KEY=你的stepfun_api_key
export ANTHROPIC_MODEL=step-3.5-flash
```

### 验证配置是否生效

无论用哪种方法，都可以用这个命令快速测试：（这种方式必须要用环境变量，才可以）

```bash
claude -p "说你好，你是什么模型"
```

![](assets/feishu-chat1.png)



能收到回复就说明配置成功。

打开飞书，给机器人发消息测试

![飞书 Bot 聊天效果](assets/feishu-chat1.png)

---

## 可选：启动 Daemon

Daemon 是后台调度器，用于定时执行 Skill（如知识库自检）。不启动也不影响聊天

```bash
make daemon     # 前台运行
make daemon-bg  # 或者后台运行
```

---

## 可选：后台运行 Gateway

日常使用建议后台运行：

```bash
make gateway-bg    # 后台启动
make gateway-logs  # 查看实时日志
make gateway-stop  # 停止
```

---

## 注意事项

### 模型能力差异

第三方服务商提供的是自家模型（如 StepFun 的 Step 系列、DeepSeek 的 DeepSeek 系列），**不是 Claude 模型**。日常对话没问题，但复杂任务需要验证。

## 常见问题

### `/model` 命令无效

使用第三方 API 时，Gateway 的 `/model sonnet`、`/model opus` 等切换命令不会真正切换模型——因为第三方 API 只有一个模型，所有别名都指向同一个模型。

### Gateway 启动后飞书没反应

1. 检查应用是否已发布（「版本管理与发布」中状态为「已上线」）
2. 检查是否开通了 `im:message` 权限
3. 检查事件订阅模式是否选了「长连接」
4. 看 Gateway 日志有没有错误

### 报错 `配置文件不存在`

检查 `.claude/secrets/feishu_app.json` 是否存在，格式是否正确（JSON 格式，三个字段都填了）

### 报错 `Missing required field 'signature'`

第三方模型返回的 thinking block 缺少 signature 字段。Gateway 已内置 monkey-patch 自动修复，如果仍出现，确认是最新版本代码

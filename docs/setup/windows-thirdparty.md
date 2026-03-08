# Windows + 第三方 API（StepFun / DeepSeek 等）

> **WIP：赶工中**，内容可能不完整，欢迎反馈。

没有 Claude Code 订阅也能用。只要服务商兼容 Anthropic API 协议（一种 AI 接口标准），配一下就行。

---

## 前置条件

- Windows 10/11
- Git、Python 3.10+、Claude Code CLI 已安装 → 没装过？看 **[环境准备指南](prerequisites-windows.md)**
  > 不需要 Claude 订阅，只需要装好 CLI
- 飞书账号
- 一个兼容 Anthropic API 的第三方服务商账号

### 目前已知兼容的服务商

| 服务商 | Base URL | 免费额度 | 备注 |
|--------|----------|----------|------|
| [StepFun](https://platform.stepfun.com/) | `https://api.stepfun.com/anthropic` | 注册送额度 | 国内直连 |
| [DeepSeek](https://platform.deepseek.com/) | `https://api.deepseek.com/anthropic` | 注册送额度 | 国内直连 |

> 只要支持 Anthropic Messages API 格式的服务商都可以，不限于以上两家。

---

## 第一步：创建飞书自建应用

和 Mac 方案完全一样（飞书配置跟操作系统无关），参考 [mac-claude.md 第一步](mac-claude.md#第一步创建飞书自建应用)。

---

## 第二步：获取第三方 API Key

API Key 是服务商给你的一串密钥，用来验证身份和计费。以 StepFun 为例：

1. 注册 [StepFun 开放平台](https://platform.stepfun.com/)
2. 进入控制台 → API Keys → 创建新 Key
3. **立即复制保存**（关掉页面后就看不到了，需要重新创建）

DeepSeek 类似：注册 → 控制台 → 创建 API Key。

---

## 第三步：下载代码 & 配置

打开 PowerShell（按 `Win + X` → 选择「终端」或「PowerShell」），逐行粘贴执行：

```powershell
# 下载项目代码
git clone https://github.com/anthropic-fans/claude-feishu-gateway.git

# 进入项目目录（后续命令都在这个目录下执行）
cd claude-feishu-gateway

# 安装 Python 依赖包
pip3 install -r requirements.txt
```

> 如果 `pip3` 找不到，试试 `pip install -r requirements.txt`。

然后创建飞书配置文件。用文件管理器进入项目的 `.claude\secrets\` 目录（没有就新建），创建 `feishu_app.json` 文件，内容如下（替换成第一步获取的真实值）：

```json
{
  "app_id": "cli_你的app_id",
  "app_secret": "你的app_secret",
  "allowed_open_id": "ou_你的open_id"
}
```

> 也可以用命令创建：
> ```powershell
> New-Item -ItemType Directory -Force -Path .claude\secrets
> @'
> {
>   "app_id": "cli_你的app_id",
>   "app_secret": "你的app_secret",
>   "allowed_open_id": "ou_你的open_id"
> }
> '@ | Out-File -Encoding utf8 .claude\secrets\feishu_app.json
> ```

`allowed_open_id` 是安全限制——只有这个飞书用户的消息会被处理，其他人发的消息会被忽略。

---

## 第四步：配置第三方 API

这一步是关键——告诉 Gateway 使用第三方 API 而不是 Claude 官方服务。

### 方法一：写入配置文件（推荐）

复制一份示例配置：

```powershell
Copy-Item config\env.conf.example config\env.conf
```

用记事本打开编辑：

```powershell
notepad config\env.conf
```

填入你的配置：

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

如果不想用配置文件，也可以在 PowerShell 中手动设置（每次开新窗口都要重新设）：

```powershell
$env:ANTHROPIC_BASE_URL = "https://api.stepfun.com/anthropic"
$env:ANTHROPIC_API_KEY = "你的stepfun_api_key"
$env:ANTHROPIC_MODEL = "step-3.5-flash"
```

### 验证配置是否生效

无论用哪种方法，都可以用这个命令快速测试：

```powershell
claude -p "说你好"
```

能收到回复就说明配置成功。

---

## 第五步：启动 & 测试

如果你安装了 Make（参考[环境准备](prerequisites-windows.md#4-安装-make可选但推荐)）：

```powershell
make check      # 检查配置
make gateway    # 启动
```

如果没装 Make，直接用 Python 启动：

```powershell
# 检查配置
python3 scripts/preflight.sh   # 暂不支持，用 make check 或跳过

# 启动 Gateway
python3 components/servers/feishu_gateway.py
```

打开飞书，给机器人发消息测试。

---

## 注意事项

### 模型能力差异

第三方服务商提供的是自家模型（如 StepFun 的 Step 系列、DeepSeek 的 DeepSeek 系列），**不是 Claude 模型**。日常对话没问题，但复杂任务（多工具协作、高级推理）可能不如 Claude 原版。

### `/model` 命令无效

使用第三方 API 时，Gateway 的 `/model sonnet`、`/model opus` 等切换命令不会真正切换模型——因为第三方 API 只有一个模型，所有别名都指向同一个模型。

### 费用

第三方 API 按调用量计费（token 数），每次对话都会消耗额度。建议：
- 先用注册赠送的免费额度测试
- 日常使用时关注服务商控制台的用量统计，避免意外消费

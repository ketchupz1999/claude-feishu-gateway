# Gateway Phase 2 Release Notes

> Date: 2026-04-24
> Status: draft

## [新增功能] 支持 Codex 与 Gemini Gateway

**What**
你现在可以把飞书 Bot 接到 Claude、Codex 或 Gemini 三种本机 Agent 运行时。通过 `components/config.yaml` 里的 `gateway_mode` 即可切换，不需要公网服务器或额外转发服务。

**Why**
之前开源版只覆盖 Claude Gateway，使用 Codex 或 Gemini 的用户需要自己维护私有改造。现在 Gateway 能复用本机 Codex / Gemini 登录态，并保留飞书侧会话续聊、历史会话、停止任务等基础能力，开源版与当前内部网关能力基本对齐。

**How**

```bash
cp components/config.example.yaml components/config.yaml

# Codex
# gateway_mode: codex

# Gemini
# gateway_mode: gemini

make gateway-codex-install
make gateway-codex-build
make gateway-codex-test
make gateway
```

使用限制：

- Codex 模式需要本机 Codex CLI / SDK 登录态，或配置对应 API key。
- Gemini 模式需要本机 Gemini CLI 登录态，或配置 `GEMINI_API_KEY`。
- Gemini 模式当前不支持飞书侧 `/model` 切换。

## [新增功能] 支持可选微信 listener

**What**
新增微信 listener，可把微信消息作为可选通道接入本机 Codex 运行时。微信登录态只保存在本地 `data/weixin_state/`，默认不会进入 git。

**Why**
之前 Gateway 主要面向飞书使用，移动端入口依赖飞书 Bot。微信 listener 让同一套本机 Agent 能扩展到微信通道，同时保持通道隔离和本地登录态管理。

**How**

```bash
make weixin-doctor
make weixin-setup
make weixin-login
```

使用限制：

- 微信 listener 需要 Node.js `>=22`。
- 当前默认接入 Codex 运行时。
- 首次使用需要本机扫码登录。

## [优化] 会话列表更接近原生 CLI

**What**
`/sessions` 现在会读取 Codex / Gemini 原生会话记录，展示用户问题、模型、时间和来源，并通过 `/switch 1` 这类序号切换会话。

**Why**
之前会话列表容易暴露长 ID，Gemini 会话还会出现 `Complex content` 这类不可读标题。现在列表更适合在飞书卡片里阅读，也避免用户手动复制长 session id。

**How**

```text
/sessions
/switch 1
/pin 1
/stop
```

使用限制：

- Codex 置顶能力由 Gateway 本地轻量状态保存，不修改 Codex 原生数据库。
- Gemini 当前只支持列出和切换会话，暂不支持置顶。

## [安全边界] 移除私有能力与凭证

**What**
本次开源同步只迁移通用 Gateway 能力，不包含个人 skill passthrough、私有凭证、交易脚本、金融链路或个人知识库数据。

**Why**
Gateway 能力应该开源复用，但个人技能、账号状态和业务脚本不应随仓库发布。明确边界可以降低误提交风险，也让外部用户更容易理解哪些能力属于通用基础设施。

**How**

- 示例配置放在 `components/config.example.yaml`。
- 本地配置 `components/config.yaml` 被 git ignore。
- 飞书 secret、微信登录态、Gateway 运行数据均保持本地存储。

## Verification

```bash
make check
make gateway-codex-build
make gateway-codex-test
make weixin-doctor
cd components/servers/weixin_listener && npm run typecheck
```

已在本机完成 Codex 与 Gemini 飞书阶段验收；微信 listener 已通过 doctor/typecheck，完整联调需要 Node.js `>=22` 环境。

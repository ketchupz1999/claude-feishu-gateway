# Weixin Listener (Codex)

目的：把微信 ClawBot 通道接到本仓库的 Codex 运行时，不走 OpenClaw 网关。

要求：

- Node.js `>=22`
- 微信登录态只落本地 `data/weixin_state/`
- 不自动复制历史账号目录，请显式执行 `make weixin-login`

## 快速使用

```bash
make weixin-setup
make weixin-login   # 扫码登录（一次即可）
make weixin-start   # 前台验证监听
```

或在子目录直接执行：

```bash
cd components/servers/weixin_listener
make setup
make login
make start
```

## 环境变量

- `AGENTS_WORKSPACE`：Codex 工作目录，默认 `process.cwd()`
- `WEIXIN_ACCOUNT_ID`：指定账号，默认使用首个已登录账号
- `WEIXIN_BASE_URL`：微信 API 基址（可选）
- `CODEX_API_KEY`：可选；不填则复用 Codex CLI 登录态
- `OPENAI_API_KEY`：可选，作为 `CODEX_API_KEY` 兜底
- `CODEX_SANDBOX_MODE`：`read-only` / `workspace-write` / `danger-full-access`
- `CODEX_APPROVAL_POLICY`：`never` / `on-request` / `on-failure` / `untrusted`

## 网关接入（listener_channels）

```yaml
listener_channels:
  weixin:
    enabled: true
    command:
      - make
      - -C
      - components/servers/weixin_listener
      - start-gateway
    env:
      AGENTS_WORKSPACE: "/path/to/agents-workspace"
      OPENCLAW_STATE_DIR: "/path/to/agents-workspace/data/weixin_state"
```

说明：
- 登录态默认写入 `OPENCLAW_STATE_DIR`（推荐仓库内 `data/weixin_state`），便于迁移机器。
- `make weixin-doctor` 可检查配置是否满足通道隔离与推荐命令。
- vendored `weixin-agent-sdk` 的许可证和来源说明见 `vendor/weixin-agent-sdk/LICENSE` 与 `vendor/weixin-agent-sdk/SOURCE.md`。

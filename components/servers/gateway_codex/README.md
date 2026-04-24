# Gateway Codex / Gemini

这个目录提供开源版的 Node Gateway：

1. 飞书入口使用 `@larksuiteoapi/node-sdk`
2. `gateway_mode: codex` 走 `@openai/codex-sdk`
3. `gateway_mode: gemini` 走 `@google/gemini-cli-core`
4. 复用原有 `data/gateway.pid`、`data/logs/*-gateway.log`、会话存储目录

开源版只保留公共 Gateway 能力：

- 支持普通聊天与控制命令
- 支持会话切换、置顶和 `/stop`
- 不包含私有 skill passthrough
- 不包含金融 / 交易 / 个人脚本 slash 命令

## 本地使用

```bash
cd components/servers/gateway_codex
npm install
npm run build
npm test
```

如需验证 Codex SDK 本机登录态，可额外运行：

```bash
npm run smoke:sdk -- "$PWD/../../.." "Reply with exactly OK and nothing else."
```

## 入口命令

```bash
make gateway-codex-build
make gateway-codex-test
make gateway-codex
make gateway-codex-bg
make gateway-codex-status
```

#!/usr/bin/env node

import process from "node:process";
import { login, start } from "weixin-agent-sdk";

import { CodexWeixinAgent } from "./codex-agent.js";

function usage(): void {
  console.log(`weixin-listener (codex)

用法:
  npm run login     扫码登录微信
  npm run start     启动微信监听并接入 Codex

可选环境变量:
  WEIXIN_BASE_URL       微信网关地址（默认 SDK 内置）
  WEIXIN_ACCOUNT_ID     指定启动账号（默认首个已登录账号）
  AGENTS_WORKSPACE      工作区根目录（默认 process.cwd()）
  CODEX_API_KEY         可选，未设置时复用 Codex CLI 登录态
  OPENAI_API_KEY        可选，作为 CODEX_API_KEY 兜底
  CODEX_SANDBOX_MODE    read-only/workspace-write/danger-full-access
  CODEX_APPROVAL_POLICY never/on-request/on-failure/untrusted`);
}

async function main(): Promise<void> {
  const command = process.argv[2];
  switch (command) {
    case "login": {
      await login({
        baseUrl: process.env.WEIXIN_BASE_URL,
        log: (msg) => console.log(msg)
      });
      return;
    }
    case "start": {
      const agent = new CodexWeixinAgent({
        workingDirectory: process.env.AGENTS_WORKSPACE ?? process.cwd(),
        onStatus: (status) => console.log(`[codex] ${status}`)
      });
      const ac = new AbortController();
      process.on("SIGINT", () => {
        console.log("\n[weixin-listener] 收到 SIGINT，正在退出...");
        ac.abort();
      });
      process.on("SIGTERM", () => {
        console.log("\n[weixin-listener] 收到 SIGTERM，正在退出...");
        ac.abort();
      });
      await start(agent, {
        accountId: process.env.WEIXIN_ACCOUNT_ID,
        abortSignal: ac.signal,
        log: (msg) => console.log(msg)
      });
      return;
    }
    default:
      usage();
      process.exitCode = 1;
  }
}

main().catch((err) => {
  console.error("[weixin-listener] fatal:", err instanceof Error ? err.stack ?? err.message : String(err));
  process.exit(1);
});
